package gpuedgecloudsim.edge_server;

import java.util.Collections;
import java.util.List;

import org.cloudbus.cloudsim.CloudletScheduler;

import edu.boun.edgecloudsim.edge_server.EdgeVM;

import gpuedgecloudsim.edge_client.GpuTask;

/**
 * VM de borda que pode dispor de uma GPU física. Quando {@code requiresGpu} é verdadeiro,
 * a VM recebe uma GPU exclusiva do host e um escalonador de GPU, ao qual são submetidas
 * as tarefas com gpu_length &gt; 0.
 */
public class GpuEdgeVM extends EdgeVM {

    private final boolean requiresGpu;
    private GpuCloudletScheduler gpuScheduler;
    private Gpu allocatedGpu;

    /**
     * @param mips         capacidade por núcleo, em MIPS
     * @param ram          em MB
     * @param bw           em Kbps
     * @param size         armazenamento, em MB
     * @param gpuScheduler escalonador de GPU; null quando requiresGpu é falso
     */
    public GpuEdgeVM(int id, int userId, double mips, int numberOfPes,
                     int ram, long bw, long size, String vmm,
                     CloudletScheduler cloudletScheduler,
                     GpuCloudletScheduler gpuScheduler,
                     boolean requiresGpu) {
        super(id, userId, mips, numberOfPes, ram, bw, size, vmm, cloudletScheduler);
        this.requiresGpu = requiresGpu;
        this.gpuScheduler = gpuScheduler;
        this.allocatedGpu = null;
    }

    public boolean requiresGpu() {
        return requiresGpu;
    }

    public boolean hasGpu() {
        return allocatedGpu != null;
    }

    public Gpu getGpu() {
        return allocatedGpu;
    }

    /** Atribui a GPU à VM e associa a ela o escalonador; null remove a atribuição. */
    public void setGpu(Gpu gpu) {
        this.allocatedGpu = gpu;
        if (gpu != null && gpuScheduler != null) {
            gpuScheduler.initialize(gpu);
        }
    }

    public GpuCloudletScheduler getGpuCloudletScheduler() {
        return gpuScheduler;
    }

    /** @return false se a VM não tiver escalonador de GPU ou se a tarefa não for admitida */
    public boolean submitGpuTask(GpuTask gpuTask) {
        if (gpuScheduler == null) {
            return false;
        }
        return gpuScheduler.submitGpuTask(gpuTask);
    }

    /** Tarefas de GPU concluídas desde a última chamada. */
    public List<GpuTask> getAndClearNewlyCompletedGpuTasks() {
        if (gpuScheduler instanceof GpuCloudletSchedulerTimeShared) {
            return ((GpuCloudletSchedulerTimeShared) gpuScheduler).getAndClearNewlyCompletedTasks();
        }
        return Collections.emptyList();
    }
}
