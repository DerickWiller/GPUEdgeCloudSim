package gpuedgecloudsim.edge_server;

import java.util.List;

/**
 * Atribuição das GPUs de um host às suas VMs, no padrão dos provisionadores do CloudSim
 * (RamProvisioner, BwProvisioner).
 */
public interface GpuProvisioner {

    /** @return false se a GPU já estiver atribuída a outra VM */
    boolean allocateGpuForVm(GpuEdgeVM vm, Gpu gpu);

    /** Libera a GPU da VM e restaura seu estado inicial. */
    void deallocateGpuForVm(GpuEdgeVM vm);

    boolean hasAvailableGpu();

    /** @return uma GPU livre, segundo a estratégia da implementação, ou null */
    Gpu getAvailableGpu();

    /** @return uma GPU livre com ao menos {@code requiredMemory} MB, ou null */
    Gpu getAvailableGpuWithMemory(long requiredMemory);

    List<Gpu> getGpuList();

    List<Gpu> getAvailableGpuList();

    List<Gpu> getAllocatedGpuList();
}
