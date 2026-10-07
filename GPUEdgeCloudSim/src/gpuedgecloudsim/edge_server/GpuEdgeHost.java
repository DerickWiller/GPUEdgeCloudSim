package gpuedgecloudsim.edge_server;

import java.util.ArrayList;
import java.util.List;

import org.cloudbus.cloudsim.Pe;
import org.cloudbus.cloudsim.Vm;
import org.cloudbus.cloudsim.VmScheduler;
import org.cloudbus.cloudsim.provisioners.BwProvisioner;
import org.cloudbus.cloudsim.provisioners.RamProvisioner;

import edu.boun.edgecloudsim.edge_server.EdgeHost;

/**
 * Host de borda com um conjunto de GPUs, além dos recursos de CPU, memória e rede do
 * EdgeHost. As GPUs são atribuídas às VMs pelo GpuProvisioner: uma VM que requer GPU só é
 * criada se houver GPU livre, e a GPU é liberada quando a VM é destruída.
 */
public class GpuEdgeHost extends EdgeHost {

    private List<Gpu> gpuList;
    private GpuProvisioner gpuProvisioner;

    public GpuEdgeHost(int id, RamProvisioner ramProvisioner,
                       BwProvisioner bwProvisioner, long storage,
                       List<? extends Pe> peList, VmScheduler vmScheduler,
                       List<Gpu> gpuList, GpuProvisioner gpuProvisioner) {
        super(id, ramProvisioner, bwProvisioner, storage, peList, vmScheduler);

        this.gpuList = new ArrayList<>(gpuList);
        this.gpuProvisioner = gpuProvisioner;

        for (Gpu gpu : this.gpuList) {
            gpu.setHost(this);
        }
    }

    public List<Gpu> getGpuList() {
        return new ArrayList<>(gpuList);
    }

    public GpuProvisioner getGpuProvisioner() {
        return gpuProvisioner;
    }

    public int getNumberOfGpus() {
        return gpuList.size();
    }

    /** @return a GPU com o identificador dado, ou null */
    public Gpu getGpu(int gpuId) {
        return gpuList.stream()
                     .filter(gpu -> gpu.getId() == gpuId)
                     .findFirst()
                     .orElse(null);
    }

    public boolean allocateGpuForVm(GpuEdgeVM vm, Gpu gpu) {
        return gpuProvisioner.allocateGpuForVm(vm, gpu);
    }

    public void deallocateGpuForVm(GpuEdgeVM vm) {
        gpuProvisioner.deallocateGpuForVm(vm);
    }

    public boolean hasAvailableGpu() {
        return gpuProvisioner.hasAvailableGpu();
    }

    public Gpu getAvailableGpu() {
        return gpuProvisioner.getAvailableGpu();
    }

    /** @return uma GPU livre com ao menos {@code requiredMemory} MB, ou null. Não é usado pela simulação. */
    public Gpu getAvailableGpuWithMemory(long requiredMemory) {
        return gpuProvisioner.getAvailableGpuWithMemory(requiredMemory);
    }

    /**
     * Utilização do host, em percentual: média simples entre a utilização de CPU (MIPS
     * reservados sobre MIPS totais) e a utilização média das GPUs. Sem GPU, apenas a de CPU.
     */
    public double getAvgUtilization() {
        double cpuUtilization = 0.0;
        if (!getVmList().isEmpty()) {
            double totalMips = getTotalMips();
            double allocatedMips = 0.0;
            for (Vm vm : getVmList()) {
                allocatedMips += vm.getCurrentRequestedTotalMips();
            }
            cpuUtilization = (allocatedMips / totalMips) * 100.0;
        }

        double gpuUtilization = getAvgGpuUtilization();

        if (gpuList.isEmpty()) {
            return cpuUtilization;
        }

        return (cpuUtilization + gpuUtilization) / 2.0;
    }

    /** Percentual (0–100). */
    public double getAvgGpuUtilization() {
        if (gpuList.isEmpty()) {
            return 0.0;
        }

        double totalUtilization = gpuList.stream()
                                        .mapToDouble(Gpu::getUtilization)
                                        .sum();

        return totalUtilization / gpuList.size();
    }

    /** Em MB. */
    public long getTotalGpuMemory() {
        return gpuList.stream()
                     .mapToLong(Gpu::getGpuMemory)
                     .sum();
    }

    /** Em MB. */
    public long getAvailableGpuMemory() {
        return gpuList.stream()
                     .mapToLong(Gpu::getAvailableMemory)
                     .sum();
    }

    /** Capacidade somada das GPUs, em MI/s. */
    public double getTotalGpuGflops() {
        return gpuList.stream()
                     .mapToDouble(Gpu::getGflops)
                     .sum();
    }

    /**
     * Cria a VM; se ela requer GPU, a criação só ocorre havendo GPU livre, que é então
     * atribuída à VM. Se a atribuição falhar, a VM é destruída.
     */
    @Override
    public boolean vmCreate(Vm vm) {
        if (vm instanceof GpuEdgeVM) {
            GpuEdgeVM gpuVm = (GpuEdgeVM) vm;

            if (gpuVm.requiresGpu() && !gpuVm.hasGpu()) {
                Gpu availableGpu = getAvailableGpu();

                if (availableGpu == null) {
                    for (Gpu gpu : getGpuList()) {
                    }
                    return false;
                }
            }
        }

        boolean created = super.vmCreate(vm);

        if (!created) {
            return false;
        }

        if (vm instanceof GpuEdgeVM) {
            GpuEdgeVM gpuVm = (GpuEdgeVM) vm;

            if (gpuVm.requiresGpu() && !gpuVm.hasGpu()) {
                Gpu availableGpu = getAvailableGpu();

                if (availableGpu == null) {
                    super.vmDestroy(vm);
                    return false;
                }

                boolean gpuAllocated = allocateGpuForVm(gpuVm, availableGpu);

                if (!gpuAllocated) {
                    super.vmDestroy(vm);
                    return false;
                }
            }
        }

        return true;
    }

    /** Libera a GPU da VM, se houver, antes de destruí-la. */
    @Override
    public void vmDestroy(Vm vm) {
        if (vm instanceof GpuEdgeVM) {
            GpuEdgeVM gpuVm = (GpuEdgeVM) vm;

            if (gpuVm.hasGpu()) {
                deallocateGpuForVm(gpuVm);
            }
        }

        super.vmDestroy(vm);
    }

    @Override
    public String toString() {
        return String.format("GpuEdgeHost[id=%d, cpus=%d, gpus=%d, location=%s]",
                           getId(), getNumberOfPes(), getNumberOfGpus(),
                           getLocation() != null ? getLocation().toString() : "unknown");
    }
}
