package gpuedgecloudsim.edge_orchestrator;

import java.util.List;

import org.cloudbus.cloudsim.Datacenter;
import org.cloudbus.cloudsim.Host;
import org.cloudbus.cloudsim.Vm;
import org.cloudbus.cloudsim.VmAllocationPolicy;

import edu.boun.edgecloudsim.core.SimManager;
import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.edge_client.Task;
import edu.boun.edgecloudsim.edge_orchestrator.EdgeOrchestrator;
import edu.boun.edgecloudsim.edge_server.EdgeServerManager;
import edu.boun.edgecloudsim.edge_server.EdgeVM;
import edu.boun.edgecloudsim.utils.Location;

import gpuedgecloudsim.edge_client.GpuTask;
import gpuedgecloudsim.edge_server.Gpu;
import gpuedgecloudsim.edge_server.GpuEdgeHost;
import gpuedgecloudsim.edge_server.GpuEdgeVM;

/**
 * Orquestrador de borda com GPU. A decisão de alocação depende da topologia:
 * <ul>
 *   <li><b>Borda homogênea</b> (toda VM possui GPU): a tarefa é alocada à VM de menor
 *       utilização média de CPU e GPU; na ausência de GPU disponível, segue para a nuvem.</li>
 *   <li><b>Borda heterogênea</b> (há VM sem GPU): tarefas de GPU são alocadas apenas a VMs
 *       com GPU e rejeitadas na falta delas; tarefas de CPU podem ocupar qualquer VM. A
 *       escolha da VM é feita por round-robin, e a nuvem não é utilizada.</li>
 * </ul>
 * A política configurada ({@code policy}) influencia apenas o score do ramo homogêneo.
 */
public class GpuEdgeOrchestrator extends EdgeOrchestrator {

    private String policy;
    private String simScenario;

    // Pesos do score HYBRID_GPU, também aplicado como política padrão.
    private static final double LATENCY_WEIGHT = 0.4;
    private static final double GPU_UTIL_WEIGHT = 0.3;
    private static final double GPU_MEMORY_WEIGHT = 0.3;

    /**
     * Identificador devolvido quando uma tarefa de GPU não encontra GPU disponível na
     * borda heterogênea. Como não corresponde à borda nem à nuvem, o GpuMobileDeviceManager
     * registra a tarefa como rejeitada por capacidade (REJECTED_DUE_TO_VM_CAPACITY), sem
     * redirecioná-la para CPU ou para a nuvem.
     */
    private static final int REJECT_NO_GPU_AVAILABLE = -1;

    /** Resultado em cache de isHeterogeneousEdge; null enquanto não calculado. */
    private Boolean heterogeneousEdge = null;

    private int cpuRoundRobinIndex = 0;
    private int gpuRoundRobinIndex = 0;

    public GpuEdgeOrchestrator(String _policy, String _simScenario) {
        this.policy = _policy;
        this.simScenario = _simScenario;
    }

    @Override
    public void initialize() {
    }

    @Override
    public void startEntity() {
    }

    @Override
    public void shutdownEntity() {
    }

    @Override
    public void processEvent(org.cloudbus.cloudsim.core.SimEvent ev) {
    }

    @Override
    public int getDeviceToOffload(Task task) {
        if (!(task instanceof GpuTask)) {
            return SimSettings.GENERIC_EDGE_DEVICE_ID;
        }

        GpuTask gpuTask = (GpuTask) task;

        if (isHeterogeneousEdge()) {
            boolean needsGpu = taskNeedsGpu(gpuTask);

            if (!needsGpu) {
                // A VM é selecionada em getVmToOffload.
                return SimSettings.GENERIC_EDGE_DEVICE_ID;
            }

            for (Datacenter datacenter : SimManager.getInstance()
                                                   .getEdgeServerManager()
                                                   .getDatacenterList()) {
                if (!isOutsideLocalServer(datacenter, gpuTask) && hasAvailableGpu(datacenter, gpuTask)) {
                    return SimSettings.GENERIC_EDGE_DEVICE_ID;
                }
            }
            return REJECT_NO_GPU_AVAILABLE;
        }

        Location taskLocation = task.getSubmittedLocation();

        List<Datacenter> edgeDatacenters = SimManager.getInstance()
                                                      .getEdgeServerManager()
                                                      .getDatacenterList();

        // O score determina apenas se há datacenter elegível: o retorno é sempre o
        // identificador genérico da borda, e a VM é selecionada em getVmToOffload.
        int bestDatacenterId = -1;
        double bestScore = Double.MAX_VALUE;

        for (Datacenter datacenter : edgeDatacenters) {
            if (isOutsideLocalServer(datacenter, gpuTask) || !hasAvailableGpu(datacenter, gpuTask)) {
                continue;
            }

            double score = calculateDatacenterScore(datacenter, gpuTask, taskLocation);

            if (score < bestScore) {
                bestScore = score;
                bestDatacenterId = datacenter.getId();
            }
        }

        if (bestDatacenterId == -1) {
            return SimSettings.CLOUD_DATACENTER_ID;
        }

        return SimSettings.GENERIC_EDGE_DEVICE_ID;
    }

    @Override
    public Vm getVmToOffload(Task task, int deviceId) {
        if (!(task instanceof GpuTask)) {
            return getAvailableEdgeVm(deviceId);
        }

        GpuTask gpuTask = (GpuTask) task;

        if (isHeterogeneousEdge()) {
            return getVmToOffloadHeterogeneous(gpuTask);
        }

        List<Datacenter> edgeDatacenters = SimManager.getInstance()
                                                      .getEdgeServerManager()
                                                      .getDatacenterList();

        if (edgeDatacenters == null || edgeDatacenters.isEmpty()) {
            return null;
        }

        // As VMs são mantidas em EdgeServerManager.vmList e podem ainda não estar
        // alocadas a um host; a alocação de host e de GPU é feita aqui, sob demanda.
        GpuEdgeVM bestVm = null;
        double bestUtilization = Double.MAX_VALUE;

        EdgeServerManager edgeServerManager =
            SimManager.getInstance().getEdgeServerManager();

        // hostIndex indexa getVmList e deve avançar em todos os hosts, inclusive nos
        // ignorados por não terem GPU, para manter o alinhamento entre host e lista de VMs.
        int hostIndex = 0;
        for (Datacenter datacenter : edgeDatacenters) {
            for (Host host : datacenter.getHostList()) {
                if (isOutsideLocalServer(host, gpuTask)) {
                    hostIndex++;
                    continue;
                }
                List<? extends EdgeVM> vmList =
                    edgeServerManager.getVmList(hostIndex);

                if (!(host instanceof GpuEdgeHost)) {
                    hostIndex++;
                    continue;
                }

                GpuEdgeHost gpuHost = (GpuEdgeHost) host;

                if (vmList != null) {
                    for (EdgeVM edgeVm : vmList) {
                        if (!(edgeVm instanceof GpuEdgeVM)) {
                            continue;
                        }

                        GpuEdgeVM gpuVm = (GpuEdgeVM) edgeVm;

                        if (!gpuVm.requiresGpu()) {
                            continue;
                        }

                        if (!host.getVmList().contains(gpuVm)) {
                            VmAllocationPolicy policy = datacenter.getVmAllocationPolicy();
                            boolean allocated = policy.allocateHostForVm(gpuVm, host);
                            if (!allocated) {
                                continue;
                            }
                        }

                        if (!gpuVm.hasGpu()) {
                            Gpu availableGpu = gpuHost.getAvailableGpu();
                            if (availableGpu != null) {
                                boolean gpuAllocated = gpuHost.allocateGpuForVm(gpuVm, availableGpu);
                                if (gpuAllocated) {
                                    gpuVm.setGpu(availableGpu);
                                } else {
                                    continue;
                                }
                            } else {
                                continue;
                            }
                        }

                        Gpu gpu = gpuVm.getGpu();
                        if (gpu.getAvailableMemory() < gpuTask.getRequiredGpuMemory()) {
                            continue;
                        }

                        if (gpuVm.getCurrentRequestedTotalMips() >= gpuVm.getMips() * gpuVm.getNumberOfPes()) {
                            continue;
                        }

                        double cpuUtil = gpuVm.getCurrentRequestedTotalMips() /
                                       (gpuVm.getMips() * gpuVm.getNumberOfPes());
                        double gpuUtil = gpu.getUtilization() / 100.0;
                        double combinedUtil = (cpuUtil + gpuUtil) / 2.0;

                        if (combinedUtil < bestUtilization) {
                            bestUtilization = combinedUtil;
                            bestVm = gpuVm;
                        }
                    }
                }

                hostIndex++;
            }
        }

        return bestVm;
    }

    /**
     * Com edge_vm_selection=LOCAL, só servem as VMs do servidor que atende o ponto de acesso
     * de submissão da tarefa; as demais são ignoradas, e não há envio pela MAN.
     */
    private boolean isOutsideLocalServer(Host host, Task task) {
        return SimSettings.getInstance().isLocalEdgeVmSelection()
                && !GpuEdgeHost.servesAccessPoint(host, task.getSubmittedLocation());
    }

    /** O datacenter fica fora da seleção só local quando nenhum dos seus hosts é local. */
    private boolean isOutsideLocalServer(Datacenter datacenter, Task task) {
        for (Host host : datacenter.getHostList()) {
            if (!isOutsideLocalServer(host, task)) {
                return false;
            }
        }
        return true;
    }

    /** Uma tarefa requer GPU quando sua aplicação tem gpu_length &gt; 0 (índice 14 da tabela). */
    private boolean taskNeedsGpu(GpuTask gpuTask) {
        double[] cfg = SimSettings.getInstance().getTaskLookUpTable()[gpuTask.getTaskType()];
        return cfg.length > 14 && cfg[14] > 0;
    }

    /**
     * A borda é considerada heterogênea quando existe ao menos uma VM sem GPU. O resultado
     * é mantido em cache, pois a topologia não se altera durante a simulação.
     *
     * <p>O critério é avaliado por VM, e não por host, porque a VM é a unidade de alocação.
     * Com uma GPU e oito VMs por servidor, todos os hosts possuem GPU, mas apenas uma VM
     * em cada oito; um critério por host trataria essa borda como homogênea e alocaria
     * também as tarefas de CPU às VMs com GPU.</p>
     */
    private boolean isHeterogeneousEdge() {
        if (heterogeneousEdge != null) {
            return heterogeneousEdge;
        }
        heterogeneousEdge = false;
        List<Datacenter> edgeDatacenters = SimManager.getInstance()
                                                     .getEdgeServerManager()
                                                     .getDatacenterList();
        if (edgeDatacenters == null) {
            return false;
        }
        EdgeServerManager edgeServerManager =
            SimManager.getInstance().getEdgeServerManager();
        int hostIndex = 0;
        for (Datacenter datacenter : edgeDatacenters) {
            for (Host host : datacenter.getHostList()) {
                if (!(host instanceof GpuEdgeHost) ||
                    ((GpuEdgeHost) host).getGpuList().isEmpty()) {
                    heterogeneousEdge = true;
                    return true;
                }
                // Um host com GPU pode conter VMs sem GPU (requiresGpu="false").
                List<? extends EdgeVM> vmList = edgeServerManager.getVmList(hostIndex);
                if (vmList != null) {
                    for (EdgeVM edgeVm : vmList) {
                        if (!(edgeVm instanceof GpuEdgeVM)
                                || !((GpuEdgeVM) edgeVm).requiresGpu()) {
                            heterogeneousEdge = true;
                            return true;
                        }
                    }
                }
                hostIndex++;
            }
        }
        return heterogeneousEdge;
    }

    /**
     * Seleção de VM na borda heterogênea. Tarefas de GPU exigem VM com GPU e memória de
     * vídeo suficiente; tarefas de CPU podem ocupar qualquer VM e não utilizam GPU. Na
     * ausência de candidata, retorna null e a tarefa é rejeitada por capacidade.
     */
    private Vm getVmToOffloadHeterogeneous(GpuTask gpuTask) {
        boolean needsGpu = taskNeedsGpu(gpuTask);

        EdgeServerManager edgeServerManager =
            SimManager.getInstance().getEdgeServerManager();
        List<Datacenter> edgeDatacenters = edgeServerManager.getDatacenterList();
        if (edgeDatacenters == null || edgeDatacenters.isEmpty()) {
            return null;
        }

        // Adota-se round-robin em vez do critério de menor utilização: sob carga baixa a
        // utilização instantânea é praticamente nula em todas as VMs, e o critério de
        // mínimo concentraria as tarefas na primeira VM da lista.
        java.util.List<GpuEdgeVM> candidates = new java.util.ArrayList<>();

        int hostIndex = 0;
        for (Datacenter datacenter : edgeDatacenters) {
            for (Host host : datacenter.getHostList()) {
                if (isOutsideLocalServer(host, gpuTask)) {
                    hostIndex++;
                    continue;
                }
                List<? extends EdgeVM> vmList = edgeServerManager.getVmList(hostIndex);
                if (vmList == null) {
                    hostIndex++;
                    continue;
                }

                for (EdgeVM edgeVm : vmList) {
                    if (!(edgeVm instanceof GpuEdgeVM)) {
                        continue;
                    }
                    GpuEdgeVM gpuVm = (GpuEdgeVM) edgeVm;

                    if (!host.getVmList().contains(gpuVm)) {
                        VmAllocationPolicy policy = datacenter.getVmAllocationPolicy();
                        if (!policy.allocateHostForVm(gpuVm, host)) {
                            continue;
                        }
                    }

                    if (needsGpu) {
                        // Não se filtra por CPU: a capacidade da tarefa de GPU é limitada
                        // pela memória de vídeo e pelo compartilhamento temporal da GPU. Como
                        // ela usa UtilizationModelFull, a CPU aparece momentaneamente a 100%,
                        // e um filtro por CPU excluiria VMs elegíveis.
                        if (!gpuVm.requiresGpu()) {
                            continue;
                        }
                        if (!gpuVm.hasGpu()) {
                            if (!(host instanceof GpuEdgeHost)) {
                                continue;
                            }
                            Gpu availableGpu = ((GpuEdgeHost) host).getAvailableGpu();
                            if (availableGpu == null ||
                                !((GpuEdgeHost) host).allocateGpuForVm(gpuVm, availableGpu)) {
                                continue;
                            }
                            gpuVm.setGpu(availableGpu);
                        }
                        Gpu gpu = gpuVm.getGpu();
                        if (gpu == null ||
                            gpu.getAvailableMemory() < gpuTask.getRequiredGpuMemory()) {
                            continue;
                        }
                        candidates.add(gpuVm);
                    } else {
                        // Não se filtra por CPU: o escalonador é de tempo compartilhado e
                        // degrada o desempenho em vez de recusar tarefas. Além disso,
                        // getCurrentRequestedTotalMips() informa a capacidade reservada, e não
                        // o uso efetivo, de modo que o filtro excluiria todas as VMs.
                        candidates.add(gpuVm);
                    }
                }
                hostIndex++;
            }
        }

        if (candidates.isEmpty()) {
            return null;
        }

        if (needsGpu) {
            GpuEdgeVM chosen = candidates.get(gpuRoundRobinIndex % candidates.size());
            gpuRoundRobinIndex++;
            return chosen;
        } else {
            GpuEdgeVM chosen = candidates.get(cpuRoundRobinIndex % candidates.size());
            cpuRoundRobinIndex++;
            return chosen;
        }
    }

    private boolean hasAvailableGpu(Datacenter datacenter, GpuTask gpuTask) {
        for (Host host : datacenter.getHostList()) {
            if (!(host instanceof GpuEdgeHost)) {
                continue;
            }

            GpuEdgeHost gpuHost = (GpuEdgeHost) host;

            for (Gpu gpu : gpuHost.getGpuList()) {
                if (gpu.isAvailable() ||
                    gpu.getAvailableMemory() >= gpuTask.getRequiredGpuMemory()) {
                    return true;
                }
            }
        }

        return false;
    }

    /** Score do datacenter segundo a política configurada; valores menores são preferidos. */
    private double calculateDatacenterScore(Datacenter datacenter,
                                           GpuTask gpuTask,
                                           Location taskLocation) {
        switch (policy) {
            case "NEAREST_GPU":
                return calculateNetworkLatency(datacenter, taskLocation);

            case "LOAD_BALANCED_GPU":
                return calculateGpuUtilization(datacenter);

            case "MEMORY_AWARE_GPU":
                return calculateMemoryPressure(datacenter);

            case "ENERGY_EFFICIENT_GPU":
                return calculateEnergyScore(datacenter);

            case "HYBRID_GPU":
            default:
                return calculateHybridScore(datacenter, taskLocation);
        }
    }

    /** Aproximação: distância euclidiana até o primeiro host multiplicada pelo atraso da LAN. */
    private double calculateNetworkLatency(Datacenter datacenter, Location taskLocation) {
        if (datacenter.getHostList().isEmpty()) {
            return Double.MAX_VALUE;
        }

        Host host = datacenter.getHostList().get(0);
        if (!(host instanceof GpuEdgeHost)) {
            return Double.MAX_VALUE;
        }

        Location datacenterLocation = ((GpuEdgeHost) host).getLocation();

        double xDiff = taskLocation.getXPos() - datacenterLocation.getXPos();
        double yDiff = taskLocation.getYPos() - datacenterLocation.getYPos();
        double distance = Math.sqrt(xDiff * xDiff + yDiff * yDiff);

        return distance * SimSettings.getInstance().getInternalLanDelay();
    }

    private double calculateGpuUtilization(Datacenter datacenter) {
        double totalUtil = 0.0;
        int gpuCount = 0;

        for (Host host : datacenter.getHostList()) {
            if (!(host instanceof GpuEdgeHost)) {
                continue;
            }

            GpuEdgeHost gpuHost = (GpuEdgeHost) host;
            for (Gpu gpu : gpuHost.getGpuList()) {
                totalUtil += gpu.getUtilization();
                gpuCount++;
            }
        }

        return gpuCount > 0 ? totalUtil / gpuCount : 100.0;
    }

    private double calculateMemoryPressure(Datacenter datacenter) {
        long totalAvailableMemory = 0;

        for (Host host : datacenter.getHostList()) {
            if (!(host instanceof GpuEdgeHost)) {
                continue;
            }

            GpuEdgeHost gpuHost = (GpuEdgeHost) host;
            totalAvailableMemory += gpuHost.getAvailableGpuMemory();
        }

        return totalAvailableMemory > 0 ? 1.0 / totalAvailableMemory : Double.MAX_VALUE;
    }

    /** O simulador não modela energia; este score equivale à utilização de GPU (LOAD_BALANCED_GPU). */
    private double calculateEnergyScore(Datacenter datacenter) {
        return calculateGpuUtilization(datacenter);
    }

    private double calculateHybridScore(Datacenter datacenter, Location taskLocation) {
        double latency = calculateNetworkLatency(datacenter, taskLocation);
        double gpuUtil = calculateGpuUtilization(datacenter);
        double memPressure = calculateMemoryPressure(datacenter);

        double normalizedLatency = latency / 100.0;
        double normalizedUtil = gpuUtil / 100.0;
        double normalizedMemory = memPressure * 1000.0;

        return (LATENCY_WEIGHT * normalizedLatency) +
               (GPU_UTIL_WEIGHT * normalizedUtil) +
               (GPU_MEMORY_WEIGHT * normalizedMemory);
    }

    /** Para tarefas que não são GpuTask: primeira VM com CPU livre no primeiro datacenter. */
    private Vm getAvailableEdgeVm(int deviceId) {
        List<Datacenter> edgeDatacenters = SimManager.getInstance()
                                                      .getEdgeServerManager()
                                                      .getDatacenterList();

        if (edgeDatacenters == null || edgeDatacenters.isEmpty()) {
            return null;
        }

        Datacenter datacenter = edgeDatacenters.get(0);

        for (Host host : datacenter.getHostList()) {
            for (Vm vm : host.getVmList()) {
                if (vm instanceof EdgeVM) {
                    EdgeVM edgeVm = (EdgeVM) vm;
                    if (edgeVm.getCurrentRequestedTotalMips() <
                        edgeVm.getMips() * edgeVm.getNumberOfPes()) {
                        return edgeVm;
                    }
                }
            }
        }

        return null;
    }
}
