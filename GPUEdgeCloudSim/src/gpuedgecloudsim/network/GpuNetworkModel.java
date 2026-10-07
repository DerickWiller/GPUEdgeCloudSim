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
 * que excedem sua capacidade. O modelo não inclui MAN nem WAN.
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

    public GpuNetworkModel(int _numberOfMobileDevices, String _simScenario) {
        super(_numberOfMobileDevices, _simScenario);
        this.numberOfMobileDevices = _numberOfMobileDevices;
        this.simScenario = _simScenario;
    }

    @Override
    public void initialize() {
        SimLogger.printLine("GpuNetworkModel initialized with PCIe bandwidth: " +
                          PCIE_BANDWIDTH_GBPS + " GB/s");
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

    /** Atraso de subida, em segundos: WLAN e, se a tarefa usa GPU, PCIe até a GPU. */
    @Override
    public double getUploadDelay(int deviceId, int datacenterId, Task task) {
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

    /** Atraso de descida, em segundos: PCIe a partir da GPU, se usada, e WLAN. */
    @Override
    public double getDownloadDelay(int deviceId, int datacenterId, Task task) {
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
