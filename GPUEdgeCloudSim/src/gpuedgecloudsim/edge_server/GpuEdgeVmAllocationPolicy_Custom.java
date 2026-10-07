package gpuedgecloudsim.edge_server;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.cloudbus.cloudsim.Host;
import org.cloudbus.cloudsim.Vm;

import edu.boun.edgecloudsim.edge_server.EdgeVmAllocationPolicy_Custom;

/**
 * Política de alocação de VMs da borda com GPU. Mantém o posicionamento definido no
 * edge_devices.xml, herdado de EdgeVmAllocationPolicy_Custom, e impede que uma VM que
 * requer GPU seja alocada a um host sem GPU. A atribuição da GPU ocorre em
 * GpuEdgeHost.vmCreate, e a liberação, na desalocação da VM.
 */
public class GpuEdgeVmAllocationPolicy_Custom extends EdgeVmAllocationPolicy_Custom {

    private int dataCenterIndex;
    private Map<Integer, GpuEdgeHost> vmToHostMap;

    public GpuEdgeVmAllocationPolicy_Custom(List<? extends Host> list,
                                             int dataCenterIndex) {
        super(list, dataCenterIndex);
        this.dataCenterIndex = dataCenterIndex;
        this.vmToHostMap = new HashMap<>();
    }

    /** O host é escolhido pela superclasse, que lê o XML e chama allocateHostForVm(vm, host). */
    @Override
    public boolean allocateHostForVm(Vm vm) {
        return super.allocateHostForVm(vm);
    }

    @Override
    public boolean allocateHostForVm(Vm vm, Host host) {
        if (!(host instanceof GpuEdgeHost) && vm instanceof GpuEdgeVM) {
            GpuEdgeVM gpuVm = (GpuEdgeVM) vm;
            if (gpuVm.requiresGpu()) {
                return false;
            }
        }

        boolean allocated = super.allocateHostForVm(vm, host);

        if (!allocated) {
            return false;
        }

        if (host instanceof GpuEdgeHost && vm instanceof GpuEdgeVM) {
            vmToHostMap.put(vm.getId(), (GpuEdgeHost) host);
        }

        return true;
    }

    @Override
    public void deallocateHostForVm(Vm vm) {
        if (vm instanceof GpuEdgeVM) {
            GpuEdgeVM gpuVm = (GpuEdgeVM) vm;
            GpuEdgeHost host = vmToHostMap.get(vm.getId());

            if (host != null && gpuVm.hasGpu()) {
                host.deallocateGpuForVm(gpuVm);
            }

            vmToHostMap.remove(vm.getId());
        }

        super.deallocateHostForVm(vm);
    }
}
