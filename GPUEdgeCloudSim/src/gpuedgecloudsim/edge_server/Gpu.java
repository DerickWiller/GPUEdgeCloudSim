package gpuedgecloudsim.edge_server;

import edu.boun.edgecloudsim.utils.SimLogger;

/**
 * GPU física de um host de borda: capacidade de processamento, memória de vídeo e
 * estado de alocação. Cada GPU é alocada com exclusividade a uma VM.
 *
 * <p>A capacidade, armazenada no campo {@code gflops}, é expressa em MI/s, na mesma escala
 * do comprimento das tarefas, e não em operações de ponto flutuante. O tempo de execução é
 * t = gpuLength / capacidade. A RTX 3050 é calibrada pelo tempo de inferência medido do
 * YOLO, 4 ms por quadro (Rodrigues et al., 2026): 91 MI / 0,004 s = 22 750 MI/s.</p>
 */
public class Gpu {

    private int id;
    private String gpuType;
    private int cudaCores;
    /** Capacidade de processamento, em MI/s (ver comentário da classe). */
    private double gflops;
    /** Memória de vídeo total, em MB. */
    private long gpuMemory;
    /** Banda da memória de vídeo, em GB/s. */
    private double memoryBandwidth;
    /** Percentual (0–100). */
    private double utilization;
    /** Memória de vídeo ocupada, em MB. */
    private long usedMemory;
    /** null quando a GPU está livre. */
    private GpuEdgeVM allocatedVm;
    private GpuEdgeHost host;

    public Gpu(int id, String gpuType, int cudaCores, double gflops,
               long gpuMemory, double memoryBandwidth) {
        this.id = id;
        this.gpuType = gpuType;
        this.cudaCores = cudaCores;
        this.gflops = gflops;
        this.gpuMemory = gpuMemory;
        this.memoryBandwidth = memoryBandwidth;
        this.utilization = 0.0;
        this.usedMemory = 0;
        this.allocatedVm = null;
        this.host = null;
    }

    /** GPU genérica, com banda de memória de 100 GB/s. */
    public Gpu(int id, int cudaCores, double gflops, long gpuMemory) {
        this(id, "Generic_GPU", cudaCores, gflops, gpuMemory, 100.0);
    }

    public int getId() {
        return id;
    }

    public String getGpuType() {
        return gpuType;
    }

    public int getCudaCores() {
        return cudaCores;
    }

    public double getGflops() {
        return gflops;
    }

    public long getGpuMemory() {
        return gpuMemory;
    }

    public double getMemoryBandwidth() {
        return memoryBandwidth;
    }

    public GpuEdgeHost getHost() {
        return host;
    }

    public double getUtilization() {
        return utilization;
    }

    public long getUsedMemory() {
        return usedMemory;
    }

    public long getAvailableMemory() {
        return gpuMemory - usedMemory;
    }

    public GpuEdgeVM getAllocatedVm() {
        return allocatedVm;
    }

    public boolean isAvailable() {
        return allocatedVm == null;
    }

    public void setHost(GpuEdgeHost host) {
        this.host = host;
    }

    /** Valores fora de [0, 100] são saturados nos limites. */
    public void setUtilization(double utilization) {
        if (utilization < 0.0) {
            this.utilization = 0.0;
        } else if (utilization > 100.0) {
            this.utilization = 100.0;
        } else {
            this.utilization = utilization;
        }
    }

    /** Valores fora de [0, gpuMemory] são saturados nos limites. */
    public void setUsedMemory(long usedMemory) {
        if (usedMemory < 0) {
            this.usedMemory = 0;
        } else if (usedMemory > gpuMemory) {
            this.usedMemory = gpuMemory;
            SimLogger.printLine("Warning: GPU " + id + " memory exceeded! Capping at " + gpuMemory + " MB");
        } else {
            this.usedMemory = usedMemory;
        }
    }

    public void setAllocatedVm(GpuEdgeVM vm) {
        this.allocatedVm = vm;
    }

    /** Reserva {@code memorySize} MB de memória de vídeo; falha se não houver espaço. */
    public boolean allocateMemory(long memorySize) {
        if (memorySize < 0) {
            SimLogger.printLine("Error: Cannot allocate negative memory on GPU " + id);
            return false;
        }

        if (usedMemory + memorySize > gpuMemory) {
            SimLogger.printLine("Error: GPU " + id + " insufficient memory. " +
                              "Required: " + memorySize + " MB, Available: " + getAvailableMemory() + " MB");
            return false;
        }

        usedMemory += memorySize;
        return true;
    }

    public boolean deallocateMemory(long memorySize) {
        if (memorySize < 0) {
            SimLogger.printLine("Error: Cannot deallocate negative memory on GPU " + id);
            return false;
        }

        if (memorySize > usedMemory) {
            SimLogger.printLine("Warning: GPU " + id + " trying to deallocate more memory than used. " +
                              "Resetting to 0.");
            usedMemory = 0;
        } else {
            usedMemory -= memorySize;
        }

        return true;
    }

    /**
     * Tempo de execução isolado, em segundos: gpuLength (MI) / capacidade (MI/s). Não é
     * usado pela simulação, cujo progresso é calculado em GpuCloudletSchedulerTimeShared.
     */
    public double calculateExecutionTime(long gpuLength) {
        if (gflops == 0) {
            SimLogger.printLine("Error: GPU " + id + " has 0 GFLOPS capacity!");
            return Double.MAX_VALUE;
        }

        return (double) gpuLength / gflops;
    }

    /** Tempo de transferência, em segundos, de {@code dataSize} MB pela memória de vídeo. */
    public double calculateDataTransferTime(long dataSize) {
        if (memoryBandwidth == 0) {
            SimLogger.printLine("Error: GPU " + id + " has 0 GB/s memory bandwidth!");
            return Double.MAX_VALUE;
        }

        double dataSizeGB = dataSize / 1024.0;
        return dataSizeGB / memoryBandwidth;
    }

    /** Libera a VM alocada e zera utilização e memória ocupada. */
    public void reset() {
        this.allocatedVm = null;
        this.utilization = 0.0;
        this.usedMemory = 0;
    }

    @Override
    public String toString() {
        return String.format("GPU[id=%d, type=%s, cudaCores=%d, gflops=%.2f, memory=%dMB, " +
                           "bandwidth=%.2fGB/s, utilization=%.2f%%, available=%s]",
                           id, gpuType, cudaCores, gflops, gpuMemory, memoryBandwidth,
                           utilization, isAvailable());
    }
}
