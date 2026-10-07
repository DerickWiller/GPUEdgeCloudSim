package gpuedgecloudsim.edge_server;

import java.util.ArrayList;
import java.util.List;

/** Atribuição exclusiva (uma GPU por VM), com seleção da primeira GPU livre (first-fit). */
public class GpuProvisionerSimple implements GpuProvisioner {

    private final List<Gpu> gpuList;

    public GpuProvisionerSimple(List<Gpu> gpuList) {
        this.gpuList = new ArrayList<>(gpuList);
    }

    @Override
    public boolean allocateGpuForVm(GpuEdgeVM vm, Gpu gpu) {
        if (gpu == null || !gpu.isAvailable()) {
            return false;
        }
        gpu.setAllocatedVm(vm);
        vm.setGpu(gpu);
        return true;
    }

    @Override
    public void deallocateGpuForVm(GpuEdgeVM vm) {
        for (Gpu gpu : gpuList) {
            if (gpu.getAllocatedVm() == vm) {
                gpu.reset();
                vm.setGpu(null);
                return;
            }
        }
    }

    @Override
    public boolean hasAvailableGpu() {
        return gpuList.stream().anyMatch(Gpu::isAvailable);
    }

    @Override
    public Gpu getAvailableGpu() {
        return gpuList.stream().filter(Gpu::isAvailable).findFirst().orElse(null);
    }

    @Override
    public Gpu getAvailableGpuWithMemory(long requiredMemory) {
        return gpuList.stream()
                      .filter(g -> g.isAvailable() && g.getAvailableMemory() >= requiredMemory)
                      .findFirst()
                      .orElse(null);
    }

    @Override
    public List<Gpu> getGpuList() {
        return new ArrayList<>(gpuList);
    }

    @Override
    public List<Gpu> getAvailableGpuList() {
        List<Gpu> available = new ArrayList<>();
        for (Gpu gpu : gpuList) {
            if (gpu.isAvailable()) available.add(gpu);
        }
        return available;
    }

    @Override
    public List<Gpu> getAllocatedGpuList() {
        List<Gpu> allocated = new ArrayList<>();
        for (Gpu gpu : gpuList) {
            if (!gpu.isAvailable()) allocated.add(gpu);
        }
        return allocated;
    }
}
