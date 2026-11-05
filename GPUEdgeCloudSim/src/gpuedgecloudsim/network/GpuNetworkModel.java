package gpuedgecloudsim.network;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.cloudbus.cloudsim.core.CloudSim;

import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.edge_client.Task;
import edu.boun.edgecloudsim.network.NetworkModel;
import edu.boun.edgecloudsim.utils.Location;
import edu.boun.edgecloudsim.utils.SimLogger;

import gpuedgecloudsim.edge_client.GpuTask;

/**
 * Modelo de rede do acesso sem fio (WLAN) entre dispositivo e servidor de borda, acrescido
 * da transferência pelo barramento PCIe para tarefas que executam na GPU:
 *
 * <pre>
 *   d_subida  = D_entrada / B_ef  +  [t_PCIe(entrada)]
 *   d_descida = D_saida   / B_ef  +  [t_PCIe(saida)]
 *   t_PCIe(D) = l_PCIe + D / B_PCIe
 * </pre>
 *
 * em que B_ef é a banda efetiva do ponto de acesso. Com contenção habilitada, a banda
 * nominal é dividida igualmente entre as transmissões simultâneas no mesmo ponto de acesso
 * (compartilhamento justo), e um buffer finito, quando configurado, descarta transmissões
 * que excedem sua capacidade.
 *
 * <p>Com {@code man_enabled}, a tarefa executada em servidor distinto do ponto de acesso
 * do dispositivo atravessa também a rede metropolitana (MAN), entre o servidor local e o
 * remoto, nos dois sentidos. O trecho da MAN é solicitado pela convenção do EdgeCloudSim:
 * origem e destino iguais a {@code GENERIC_EDGE_DEVICE_ID}. O modelo não inclui WAN.</p>
 */
public class GpuNetworkModel extends NetworkModel {

    /** Banda do PCIe 3.0 x16, em GB/s (PCI-SIG, 2010). */
    private static final double PCIE_BANDWIDTH_GBPS = 15.75;

    /** Latência fixa por travessia do PCIe, em ms (valor adotado). */
    private static final double PCIE_LATENCY_MS = 0.5;

    private int numberOfMobileDevices;
    private String simScenario;

    /**
     * Transmissões em curso por ponto de acesso: para cada wlan_id, pares
     * {instante de término, volume em KB}. O número de pares determina a divisão da banda;
     * a soma dos volumes, a ocupação do buffer.
     *
     * <p>Registra-se o instante de término, e não um contador, para dispensar eventos de
     * fim de transmissão: as entradas expiradas são descartadas a cada consulta, com base
     * no relógio da simulação.</p>
     */
    private final Map<Integer, List<double[]>> ongoingTransmissions = new HashMap<>();

    /** Atraso nulo sinaliza enlace saturado, convenção do EdgeCloudSim; o chamador registra falha por banda. */
    private static final double LINK_SATURATED = 0.0;

    /**
     * Intervalo de reestimação das taxas da MAN, em s: o mesmo período de atualização da
     * fila M/M/1 do sample_app4 do EdgeCloudSim (Sonmez et al., 2019).
     */
    private static final double MAN_UPDATE_INTERVAL = 5.0;

    /**
     * Atraso máximo da MAN, em s; acima dele o enlace é tratado como saturado, como no
     * sample_app4 do EdgeCloudSim (Sonmez et al., 2019).
     */
    private static final double MAN_MAX_DELAY = 15.0;

    /** Trechos da MAN por sentido; o enlace é tratado como full-duplex. */
    private ManLink manUplink;
    private ManLink manDownlink;

    public GpuNetworkModel(int _numberOfMobileDevices, String _simScenario) {
        super(_numberOfMobileDevices, _simScenario);
        this.numberOfMobileDevices = _numberOfMobileDevices;
        this.simScenario = _simScenario;
    }

    @Override
    public void initialize() {
        SimSettings settings = SimSettings.getInstance();
        // A banda nula tornaria toda transferência pela MAN uma saturação aparente, e ids
        // de dispositivo a partir de GENERIC_EDGE_DEVICE_ID colidiriam com o trecho da MAN.
        if (settings.isManEnabled() && settings.getManBandwidth() <= 0) {
            throw new IllegalStateException("man_enabled=true exige man_bandwidth > 0");
        }
        if (settings.isManEnabled() && numberOfMobileDevices > SimSettings.GENERIC_EDGE_DEVICE_ID) {
            throw new IllegalStateException("man_enabled=true admite no máximo "
                    + SimSettings.GENERIC_EDGE_DEVICE_ID + " dispositivos");
        }

        manUplink = new ManLink(getWeightedMeanDataKB(5));
        manDownlink = new ManLink(getWeightedMeanDataKB(6));

        SimLogger.printLine("GpuNetworkModel initialized with PCIe bandwidth: " +
                          PCIE_BANDWIDTH_GBPS + " GB/s");
        SimLogger.printLine("GpuNetworkModel MAN: " +
                          (SimSettings.getInstance().isManEnabled()
                              ? "ON (" + SimSettings.getInstance().getManBandwidth() + " Kbps, "
                                + SimSettings.getInstance().getInternalLanDelay() + " s)"
                              : "OFF"));
        SimLogger.printLine("GpuNetworkModel WLAN contention: " +
                          (SimSettings.getInstance().isWlanContentionEnabled()
                              ? "ON (banda repartida entre transmissões simultâneas)"
                              : "OFF (banda nominal por fluxo — modelo histórico)"));
    }

    /**
     * Ponto de acesso que atende a tarefa. Sem localização conhecida, adota-se um enlace
     * único (0), hipótese conservadora: pode superestimar a contenção, nunca subestimá-la.
     */
    private int getWlanId(Task task) {
        Location location = task.getSubmittedLocation();
        return (location == null) ? 0 : location.getServingWlanId();
    }

    /**
     * Banda, em Kbps, atribuída a uma transmissão iniciada no instante atual: a nominal
     * dividida pelo número de transmissões ativas no ponto de acesso, incluída a nova.
     * Subida e descida compartilham o mesmo meio.
     *
     * <p>Aproximação: a banda é fixada no início da transmissão e não é reavaliada durante
     * ela, como na tabela empírica do EdgeCloudSim. Subestima-se a contenção quando o número
     * de fluxos cresce durante a transmissão, e superestima-se quando decresce.</p>
     */
    private double getSharedBandwidth(int wlanId, double bandwidthKbps) {
        if (!SimSettings.getInstance().isWlanContentionEnabled()) {
            return bandwidthKbps;
        }
        return bandwidthKbps / Math.max(1, countActiveTransmissions(wlanId) + 1);
    }

    /** Transmissões ainda ativas no ponto de acesso; as encerradas são removidas. */
    private List<double[]> getActiveTransmissions(int wlanId) {
        List<double[]> ongoing = ongoingTransmissions.get(wlanId);
        if (ongoing == null) {
            return java.util.Collections.emptyList();
        }
        double now = CloudSim.clock();
        ongoing.removeIf(entry -> entry[0] <= now);
        return ongoing;
    }

    private int countActiveTransmissions(int wlanId) {
        return getActiveTransmissions(wlanId).size();
    }

    /** Volume, em KB, ainda não entregue pelas transmissões ativas. */
    private double getPendingBacklogKB(int wlanId) {
        double backlog = 0;
        for (double[] entry : getActiveTransmissions(wlanId)) {
            backlog += entry[1];
        }
        return backlog;
    }

    /**
     * Verifica se a transmissão excederia o buffer do enlace. Com buffer finito, a sobrecarga
     * sustentada converte-se em perda; com buffer infinito (tamanho 0), apenas em atraso
     * crescente.
     */
    private boolean bufferWouldOverflow(int wlanId, double dataKB) {
        double bufferKB = SimSettings.getInstance().getWlanBufferSizeKB();
        if (!SimSettings.getInstance().isWlanContentionEnabled() || bufferKB <= 0) {
            return false;
        }
        return getPendingBacklogKB(wlanId) + dataKB > bufferKB;
    }

    /** Registra uma transmissão de {@code dataKB} KB que ocupa o enlace por {@code duration} s. */
    private void registerTransmission(int wlanId, double duration, double dataKB) {
        if (!SimSettings.getInstance().isWlanContentionEnabled() || duration <= 0) {
            return;
        }
        ongoingTransmissions
            .computeIfAbsent(wlanId, k -> new ArrayList<>())
            .add(new double[] { CloudSim.clock() + duration, dataKB });
    }

    /**
     * Tamanho médio dos dados das aplicações, em KB, ponderado pela proporção de uso; é a
     * estimativa inicial do tamanho das transferências pela MAN. O índice segue a tabela de
     * aplicações: 5 para a subida e 6 para a descida.
     */
    private double getWeightedMeanDataKB(int lookUpIndex) {
        double[][] table = SimSettings.getInstance().getTaskLookUpTable();
        double weightedSum = 0;
        double weightTotal = 0;
        for (double[] app : table) {
            weightedSum += app[0] * app[lookUpIndex];
            weightTotal += app[0];
        }
        return (weightTotal > 0) ? weightedSum / weightTotal : 0;
    }

    /**
     * Um sentido da MAN como fila M/M/1 compartilhada pelo tráfego entre servidores de borda
     * (Sonmez et al., 2018, 2019): d_MAN = 1 / (mu - lambda) + d_prop, com mu = B_MAN / (8 S),
     * lambda e S (KB) medidos no intervalo anterior, B_MAN em Kbps e d_prop o
     * lan_internal_delay (s). As chegadas são tratadas como Poisson em cada intervalo
     * (MMPP/M/1), mesmo com carga periódica.
     */
    private static final class ManLink {
        private double arrivalRate = 0;
        private double meanSizeKB;
        private double intervalStart = 0;
        private int intervalCount = 0;
        private double intervalSizeKB = 0;

        /**
         * O primeiro intervalo assume o enlace ocioso (lambda = 0); ele termina em 5 s,
         * dentro do período de aquecimento.
         */
        ManLink(double initialMeanSizeKB) {
            this.meanSizeKB = initialMeanSizeKB;
        }

        private void refreshEstimates(double now) {
            double elapsed = now - intervalStart;
            if (elapsed < MAN_UPDATE_INTERVAL) {
                return;
            }
            arrivalRate = intervalCount / elapsed;
            if (intervalCount > 0) {
                meanSizeKB = intervalSizeKB / intervalCount;
            }
            intervalStart = now;
            intervalCount = 0;
            intervalSizeKB = 0;
        }

        /** Atraso, em segundos, de uma transferência de {@code dataKB} KB iniciada agora. */
        double getDelay(double dataKB) {
            refreshEstimates(CloudSim.clock());
            intervalCount++;
            intervalSizeKB += dataKB;
            return currentDelay(dataKB);
        }

        /**
         * Atraso pela fila com as estimativas vigentes, sem registrar a transferência;
         * LINK_SATURATED quando lambda &ge; mu ou o atraso excede MAN_MAX_DELAY.
         */
        double currentDelay(double dataKB) {
            double sizeKbit = 8 * ((meanSizeKB > 0) ? meanSizeKB : dataKB);
            double serviceRate = SimSettings.getInstance().getManBandwidth() / sizeKbit;
            if (serviceRate <= arrivalRate) {
                return LINK_SATURATED;
            }
            double delay = 1.0 / (serviceRate - arrivalRate)
                    + SimSettings.getInstance().getInternalLanDelay();
            return (delay > MAN_MAX_DELAY) ? LINK_SATURATED : delay;
        }
    }

    /**
     * Atraso estimado de ida e volta pela MAN, em segundos, para os dados de subida e de
     * descida da tarefa. Usa as estimativas do intervalo vigente sem contar a tarefa no
     * tráfego medido, de modo que a consulta do orquestrador não altera lambda. Retorna
     * infinito quando algum sentido está saturado.
     */
    public double estimateManRoundTripDelay(Task task) {
        // Sem a renovação, um λ alto que levasse o orquestrador a evitar a MAN nunca seria
        // reestimado, pois só as transferências efetivas renovam o intervalo.
        manUplink.refreshEstimates(CloudSim.clock());
        manDownlink.refreshEstimates(CloudSim.clock());
        double up = manUplink.currentDelay(task.getCloudletFileSize());
        double down = manDownlink.currentDelay(task.getCloudletOutputSize());
        if (up == LINK_SATURATED || down == LINK_SATURATED) {
            return Double.POSITIVE_INFINITY;
        }
        return up + down;
    }

    /** Origem e destino genéricos de borda identificam o trecho da MAN, como no EdgeCloudSim. */
    private static boolean isManHop(int sourceId, int destinationId) {
        return sourceId == SimSettings.GENERIC_EDGE_DEVICE_ID
                && destinationId == SimSettings.GENERIC_EDGE_DEVICE_ID;
    }

    /**
     * Atraso de subida, em segundos. No trecho da MAN, o do servidor local ao remoto; nos
     * demais casos, WLAN e, se a tarefa usa GPU, PCIe até a GPU.
     */
    @Override
    public double getUploadDelay(int deviceId, int datacenterId, Task task) {
        if (isManHop(deviceId, datacenterId)) {
            return manUplink.getDelay(task.getCloudletFileSize());
        }
        // getWlanBandwidth() retorna Kbps, apesar do nome; logo Kbit / Kbps resulta em segundos.
        double wlanBandwidthKbps = SimSettings.getInstance().getWlanBandwidth();
        double dataKB = task.getCloudletFileSize();
        double dataKbit = dataKB * 8;
        int wlanId = getWlanId(task);
        if (bufferWouldOverflow(wlanId, dataKB)) {
            return LINK_SATURATED;
        }
        double effectiveBandwidthKbps = getSharedBandwidth(wlanId, wlanBandwidthKbps);
        double wlanUploadDelay = dataKbit / effectiveBandwidthKbps;
        registerTransmission(wlanId, wlanUploadDelay, dataKB);

        // Toda tarefa do simulador é instância de GpuTask, inclusive as de CPU; o custo do
        // PCIe incide apenas sobre as que efetivamente executam na GPU (gpu_length > 0).
        if (!(task instanceof GpuTask) || ((GpuTask) task).getGpuLength() <= 0) {
            return wlanUploadDelay;
        }

        GpuTask gpuTask = (GpuTask) task;

        double gpuInputDataMB = gpuTask.getGpuInputData();
        double gpuInputDataGB = gpuInputDataMB / 1024.0;

        double pcieTransferTime = (PCIE_LATENCY_MS / 1000.0) +
                                 (gpuInputDataGB / PCIE_BANDWIDTH_GBPS);

        double totalDelay = wlanUploadDelay + pcieTransferTime;

        SimLogger.printLine(String.format(
            "  GPU Upload Delay: WLAN=%.3fs, PCIe=%.3fs, Total=%.3fs",
            wlanUploadDelay, pcieTransferTime, totalDelay
        ));

        return totalDelay;
    }

    /**
     * Atraso de descida, em segundos. No trecho da MAN, o do servidor remoto ao local; nos
     * demais casos, PCIe a partir da GPU, se usada, e WLAN. Com MAN, o PCIe fica no trecho
     * WLAN, e não junto da GPU remota: o total é o mesmo, muda só a ordem dos trechos.
     */
    @Override
    public double getDownloadDelay(int deviceId, int datacenterId, Task task) {
        if (isManHop(deviceId, datacenterId)) {
            return manDownlink.getDelay(task.getCloudletOutputSize());
        }
        double wlanBandwidthKbps = SimSettings.getInstance().getWlanBandwidth();
        double dataKB = task.getCloudletOutputSize();
        double dataKbit = dataKB * 8;
        int wlanId = getWlanId(task);
        if (bufferWouldOverflow(wlanId, dataKB)) {
            return LINK_SATURATED;
        }
        double effectiveBandwidthKbps = getSharedBandwidth(wlanId, wlanBandwidthKbps);
        double wlanDownloadDelay = dataKbit / effectiveBandwidthKbps;
        registerTransmission(wlanId, wlanDownloadDelay, dataKB);

        if (!(task instanceof GpuTask) || ((GpuTask) task).getGpuLength() <= 0) {
            return wlanDownloadDelay;
        }

        GpuTask gpuTask = (GpuTask) task;

        double gpuOutputDataMB = gpuTask.getGpuOutputData();
        double gpuOutputDataGB = gpuOutputDataMB / 1024.0;

        double pcieTransferTime = (PCIE_LATENCY_MS / 1000.0) +
                                 (gpuOutputDataGB / PCIE_BANDWIDTH_GBPS);

        double totalDelay = pcieTransferTime + wlanDownloadDelay;

        SimLogger.printLine(String.format(
            "  GPU Download Delay: PCIe=%.3fs, WLAN=%.3fs, Total=%.3fs",
            pcieTransferTime, wlanDownloadDelay, totalDelay
        ));

        return totalDelay;
    }

    // Os eventos de início e fim de transmissão não são utilizados: a contenção é
    // acompanhada pelos instantes de término registrados em ongoingTransmissions.
    @Override
    public void uploadStarted(Location accessPointLocation, int destDeviceId) {
    }

    @Override
    public void uploadFinished(Location accessPointLocation, int destDeviceId) {
    }

    @Override
    public void downloadStarted(Location accessPointLocation, int sourceDeviceId) {
    }

    @Override
    public void downloadFinished(Location accessPointLocation, int sourceDeviceId) {
    }

    /** Soma dos atrasos de subida e descida, em segundos. Não é usado pela simulação. */
    public double getTotalGpuNetworkOverhead(GpuTask gpuTask, int deviceId, int datacenterId) {
        double uploadDelay = getUploadDelay(deviceId, datacenterId, gpuTask);
        double downloadDelay = getDownloadDelay(deviceId, datacenterId, gpuTask);

        return uploadDelay + downloadDelay;
    }

    /** Tempo de transferência pelo PCIe, em segundos, para {@code dataSizeMB} MB. Não é usado pela simulação. */
    public double getPcieTransferTime(double dataSizeMB) {
        double dataSizeGB = dataSizeMB / 1024.0;
        return (PCIE_LATENCY_MS / 1000.0) + (dataSizeGB / PCIE_BANDWIDTH_GBPS);
    }

    public static double getPcieBandwidth() {
        return PCIE_BANDWIDTH_GBPS;
    }

    public static double getPcieLatency() {
        return PCIE_LATENCY_MS;
    }
}
