package gpuedgecloudsim.edge_server;

import java.util.List;

import gpuedgecloudsim.edge_client.GpuTask;

/** Política de escalonamento das tarefas executadas em uma única GPU. */
public interface GpuCloudletScheduler {

    void initialize(Gpu gpu);

    /** @return false se a tarefa não for admitida */
    boolean submitGpuTask(GpuTask gpuTask);

    boolean removeGpuTask(GpuTask gpuTask);

    /**
     * Contabiliza o progresso até {@code currentTime}, em segundos.
     *
     * @return instante do próximo evento previsto, ou Double.MAX_VALUE se não houver
     */
    double updateGpuTaskProcessing(double currentTime);

    List<GpuTask> getRunningGpuTasks();

    /** Número de tarefas em execução, sem copiar a lista. */
    int getRunningGpuTaskCount();

    List<GpuTask> getWaitingGpuTasks();

    List<GpuTask> getCompletedGpuTasks();

    /** Percentual (0–100). */
    double getGpuUtilization();

    boolean hasRunningTasks();

    Gpu getGpu();
}
