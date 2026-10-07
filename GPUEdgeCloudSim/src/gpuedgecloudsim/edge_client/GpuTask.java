package gpuedgecloudsim.edge_client;

import org.cloudbus.cloudsim.UtilizationModel;

import edu.boun.edgecloudsim.edge_client.Task;

/**
 * Tarefa com uma parcela de processamento em CPU (cloudletLength, em MI) e outra em GPU
 * (gpuLength, também em MI), além da memória de vídeo exigida e dos volumes transferidos
 * entre CPU e GPU. Tarefas exclusivamente de CPU têm gpuLength = 0.
 *
 * <p>Unidades: comprimentos em MI, dados de CPU em KB, dados de GPU e memória em MB,
 * tempos em segundos de simulação.</p>
 */
public class GpuTask extends Task {

    private long gpuLength;
    private long gpuInputData;
    private long gpuOutputData;
    private long requiredGpuMemory;
    /** Percentual (0–100). */
    private double expectedGpuUtilization;

    // Métricas registradas durante a execução.
    /** -1 enquanto a tarefa não for executada em uma GPU. */
    private int executedGpuId;
    /** Não preenchido pela simulação; vale 0. */
    private double gpuDataTransferTime;
    private double gpuExecutionTime;
    /** Não preenchido pela simulação; vale 0. */
    private double gpuDataBackTime;
    /** Utilização da GPU no término da tarefa; registrada, mas não lida. */
    private double actualGpuUtilization;
    private double gpuStartTime;
    private double gpuFinishTime;

    public GpuTask(int mobileDeviceId, int cloudletId, long cloudletLength,
                   int pesNumber, long cloudletFileSize, long cloudletOutputSize,
                   UtilizationModel utilizationModelCpu,
                   UtilizationModel utilizationModelRam,
                   UtilizationModel utilizationModelBw,
                   long gpuLength, long gpuInputData, long gpuOutputData,
                   long requiredGpuMemory) {
        super(mobileDeviceId, cloudletId, cloudletLength, pesNumber,
              cloudletFileSize, cloudletOutputSize, utilizationModelCpu,
              utilizationModelRam, utilizationModelBw);

        this.gpuLength = gpuLength;
        this.gpuInputData = gpuInputData;
        this.gpuOutputData = gpuOutputData;
        this.requiredGpuMemory = requiredGpuMemory;
        this.expectedGpuUtilization = 100.0;

        this.executedGpuId = -1;
        this.gpuDataTransferTime = 0.0;
        this.gpuExecutionTime = 0.0;
        this.gpuDataBackTime = 0.0;
        this.actualGpuUtilization = 0.0;
        this.gpuStartTime = 0.0;
        this.gpuFinishTime = 0.0;
    }

    /** Construtor sem dispositivo associado e sem modelos de utilização. */
    public GpuTask(int cloudletId, int taskType, long cloudletLength,
                   int pesNumber, long cloudletFileSize, long cloudletOutputSize,
                   long gpuLength, long gpuInputData, long gpuOutputData,
                   long requiredGpuMemory) {
        this(-1, cloudletId, cloudletLength, pesNumber, cloudletFileSize, cloudletOutputSize,
             null, null, null, gpuLength, gpuInputData, gpuOutputData, requiredGpuMemory);
        this.setTaskType(taskType);
    }

    public long getGpuLength() {
        return gpuLength;
    }

    public long getGpuInputData() {
        return gpuInputData;
    }

    public long getGpuOutputData() {
        return gpuOutputData;
    }

    public long getRequiredGpuMemory() {
        return requiredGpuMemory;
    }

    public double getExpectedGpuUtilization() {
        return expectedGpuUtilization;
    }

    public int getExecutedGpuId() {
        return executedGpuId;
    }

    public double getGpuDataTransferTime() {
        return gpuDataTransferTime;
    }

    public double getGpuExecutionTime() {
        return gpuExecutionTime;
    }

    public double getGpuDataBackTime() {
        return gpuDataBackTime;
    }

    public double getActualGpuUtilization() {
        return actualGpuUtilization;
    }

    public double getGpuStartTime() {
        return gpuStartTime;
    }

    public double getGpuFinishTime() {
        return gpuFinishTime;
    }

    public void setExecutedGpuId(int gpuId) {
        this.executedGpuId = gpuId;
    }

    public void setGpuDataTransferTime(double time) {
        this.gpuDataTransferTime = time;
    }

    public void setGpuExecutionTime(double time) {
        this.gpuExecutionTime = time;
    }

    public void setGpuDataBackTime(double time) {
        this.gpuDataBackTime = time;
    }

    public void setActualGpuUtilization(double utilization) {
        this.actualGpuUtilization = utilization;
    }

    public void setGpuStartTime(double time) {
        this.gpuStartTime = time;
    }

    public void setGpuFinishTime(double time) {
        this.gpuFinishTime = time;
    }

    public void setExpectedGpuUtilization(double utilization) {
        this.expectedGpuUtilization = utilization;
    }

    /** Tempo total na GPU: transferência de entrada, execução e transferência de saída. */
    public double getTotalGpuTime() {
        return gpuDataTransferTime + gpuExecutionTime + gpuDataBackTime;
    }

    public boolean requiresGpu() {
        return gpuLength > 0;
    }

    /** Fração do processamento total atribuída à GPU: gpuLength / (cloudletLength + gpuLength). */
    public double getGpuIntensity() {
        long totalLength = getCloudletLength() + gpuLength;
        if (totalLength == 0) {
            return 0.0;
        }
        return (double) gpuLength / totalLength;
    }

    /** Não é usado pela simulação: a admissão é decidida na alocação de memória da GPU. */
    public boolean hasEnoughGpuMemory(long availableMemory) {
        return availableMemory >= requiredGpuMemory;
    }

    @Override
    public String toString() {
        return String.format("GpuTask[id=%d, cpuLength=%d MI, gpuLength=%d GFLOPS, " +
                           "gpuMemory=%d MB, gpuIntensity=%.2f, executedOnGpu=%d]",
                           getCloudletId(), getCloudletLength(), gpuLength,
                           requiredGpuMemory, getGpuIntensity(), executedGpuId);
    }
}
