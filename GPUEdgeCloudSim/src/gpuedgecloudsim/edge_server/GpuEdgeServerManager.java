package gpuedgecloudsim.edge_server;

import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

import org.cloudbus.cloudsim.Datacenter;
import org.cloudbus.cloudsim.DatacenterCharacteristics;
import org.cloudbus.cloudsim.Host;
import org.cloudbus.cloudsim.Pe;
import org.cloudbus.cloudsim.Storage;
import org.cloudbus.cloudsim.Vm;
import org.cloudbus.cloudsim.VmAllocationPolicy;
import org.cloudbus.cloudsim.VmSchedulerTimeShared;
import org.cloudbus.cloudsim.provisioners.BwProvisionerSimple;
import org.cloudbus.cloudsim.provisioners.PeProvisionerSimple;
import org.cloudbus.cloudsim.provisioners.RamProvisionerSimple;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.edge_server.EdgeServerManager;
import edu.boun.edgecloudsim.edge_server.EdgeVM;
import edu.boun.edgecloudsim.utils.Location;

/**
 * Constrói a infraestrutura de borda a partir do edge_devices.xml: um GpuDatacenter por
 * elemento {@code <datacenter>}, com hosts GpuEdgeHost e VMs GpuEdgeVM. Em relação ao
 * formato do EdgeCloudSim, o arquivo admite GPUs por host e o atributo requiresGpu por VM:
 *
 * <pre>{@code
 * <host> ...
 *   <gpus><gpu><type/><cudaCores/><gflops/><memory/><bandwidth/></gpu></gpus>
 *   <VMs><VM vmm="Xen" requiresGpu="true"> ... </VM></VMs>
 * </host>
 * }</pre>
 *
 * em que gflops é a capacidade em MI/s, memory é dado em MB e bandwidth em GB/s.
 */
public class GpuEdgeServerManager extends EdgeServerManager {

    /**
     * Banda de cada host, em Kbps, dividida igualmente entre suas VMs. Atua apenas como
     * recurso de admissão do CloudSim; o atraso de rede é calculado no GpuNetworkModel.
     */
    private static final long HOST_BANDWIDTH = 100000;

    private int hostIdCounter;
    private int vmIdCounter;

    public GpuEdgeServerManager() {
        super();
        this.hostIdCounter = 0;
        this.vmIdCounter = 0;
    }

    @Override
    public void initialize() {
    }

    @Override
    public VmAllocationPolicy getVmAllocationPolicy(List<? extends Host> list,
                                                     int dataCenterIndex) {
        return new GpuEdgeVmAllocationPolicy_Custom(list, dataCenterIndex);
    }

    @Override
    public void startDatacenters() throws Exception {
        Document doc = SimSettings.getInstance().getEdgeDevicesDocument();
        NodeList datacenterList = doc.getElementsByTagName("datacenter");

        for (int i = 0; i < datacenterList.getLength(); i++) {
            Node datacenterNode = datacenterList.item(i);
            Element datacenterElement = (Element) datacenterNode;

            Datacenter datacenter = createGpuDatacenter(i, datacenterElement);
            localDatacenters.add(datacenter);
        }
    }

    @Override
    public void terminateDatacenters() {
        for (Datacenter datacenter : localDatacenters) {
            datacenter.shutdownEntity();
        }

        localDatacenters.clear();
    }

    /**
     * Cria as VMs de cada host. vmList é indexada pela ordem dos hosts no XML, e essa
     * ordem é a mesma usada pelo orquestrador ao percorrer os hosts.
     */
    @Override
    public void createVmList(int brokerId) {
        Document doc = SimSettings.getInstance().getEdgeDevicesDocument();
        NodeList datacenterList = doc.getElementsByTagName("datacenter");

        int vmListIndex = 0;

        for (int i = 0; i < datacenterList.getLength(); i++) {
            Node datacenterNode = datacenterList.item(i);
            Element datacenterElement = (Element) datacenterNode;
            NodeList hostNodeList = datacenterElement.getElementsByTagName("host");

            for (int j = 0; j < hostNodeList.getLength(); j++) {
                vmList.add(new ArrayList<EdgeVM>());

                Node hostNode = hostNodeList.item(j);
                Element hostElement = (Element) hostNode;
                NodeList vmNodeList = hostElement.getElementsByTagName("VM");

                // A banda do host é dividida entre as VMs, como no DefaultEdgeServerManager.
                // O BwProvisionerSimple só cria a VM se o host tiver banda livre suficiente;
                // atribuir a cada VM a banda inteira do host impediria a criação de todas as
                // VMs além da primeira.
                long vmBandwidth = HOST_BANDWIDTH / Math.max(1, vmNodeList.getLength());

                for (int k = 0; k < vmNodeList.getLength(); k++) {
                    Node vmNode = vmNodeList.item(k);
                    Element vmElement = (Element) vmNode;

                    String vmm = vmElement.getAttribute("vmm");
                    boolean requiresGpu = Boolean.parseBoolean(
                        vmElement.getAttribute("requiresGpu"));

                    int numOfCores = Integer.parseInt(
                        vmElement.getElementsByTagName("core").item(0).getTextContent());
                    double mips = Double.parseDouble(
                        vmElement.getElementsByTagName("mips").item(0).getTextContent());
                    int ram = Integer.parseInt(
                        vmElement.getElementsByTagName("ram").item(0).getTextContent());
                    long storage = Long.parseLong(
                        vmElement.getElementsByTagName("storage").item(0).getTextContent());

                    GpuEdgeVM vm = new GpuEdgeVM(
                        vmIdCounter,
                        brokerId,
                        mips,
                        numOfCores,
                        ram,
                        vmBandwidth,
                        storage,
                        vmm,
                        new org.cloudbus.cloudsim.CloudletSchedulerTimeShared(),
                        requiresGpu ? new GpuCloudletSchedulerTimeShared() : null,
                        requiresGpu
                    );

                    vmList.get(vmListIndex).add(vm);
                    vmIdCounter++;
                }

                vmListIndex++;
                hostIdCounter++;
            }
        }
    }

    /** Média, entre todos os hosts, da utilização de cada host (GpuEdgeHost.getAvgUtilization). */
    @Override
    public double getAvgUtilization() {
        double totalUtilization = 0.0;
        int numHosts = 0;

        for (Datacenter datacenter : localDatacenters) {
            List<? extends Host> hostList = datacenter.getHostList();

            for (Host host : hostList) {
                if (host instanceof GpuEdgeHost) {
                    GpuEdgeHost gpuHost = (GpuEdgeHost) host;
                    totalUtilization += gpuHost.getAvgUtilization();
                } else {
                    double cpuUtil = 0.0;
                    if (!host.getVmList().isEmpty()) {
                        double totalMips = host.getTotalMips();
                        double allocatedMips = 0.0;
                        for (Vm vm : host.getVmList()) {
                            allocatedMips += vm.getCurrentRequestedTotalMips();
                        }
                        cpuUtil = (allocatedMips / totalMips) * 100.0;
                    }
                    totalUtilization += cpuUtil;
                }
                numHosts++;
            }
        }

        return numHosts > 0 ? totalUtilization / numHosts : 0.0;
    }

    private Datacenter createGpuDatacenter(int dataCenterIndex,
                                            Element datacenterElement) throws Exception {

        String arch = datacenterElement.getAttribute("arch");
        String os = datacenterElement.getAttribute("os");
        String vmm = datacenterElement.getAttribute("vmm");
        double costPerBw = Double.parseDouble(
            datacenterElement.getElementsByTagName("costPerBw").item(0).getTextContent());

        List<GpuEdgeHost> hostList = createGpuHosts(datacenterElement);

        double time_zone = 3.0;
        double costPerSec = 0.0;
        double costPerMem = 0.0;
        double costPerStorage = 0.0;

        LinkedList<Storage> storageList = new LinkedList<>();

        DatacenterCharacteristics characteristics = new DatacenterCharacteristics(
            arch, os, vmm, new ArrayList<>(hostList), time_zone, costPerSec,
            costPerMem, costPerStorage, costPerBw);

        String datacenterName = "GpuEdgeDatacenter_" + dataCenterIndex;
        VmAllocationPolicy vmAllocationPolicy = getVmAllocationPolicy(hostList, dataCenterIndex);

        GpuDatacenter datacenter = new GpuDatacenter(
            datacenterName,
            characteristics,
            vmAllocationPolicy,
            storageList,
            0
        );

        return datacenter;
    }

    private List<GpuEdgeHost> createGpuHosts(Element datacenterElement) {
        List<GpuEdgeHost> hostList = new ArrayList<>();

        NodeList hostNodeList = datacenterElement.getElementsByTagName("host");

        for (int i = 0; i < hostNodeList.getLength(); i++) {
            Node hostNode = hostNodeList.item(i);
            Element hostElement = (Element) hostNode;

            int numOfCores = Integer.parseInt(
                hostElement.getElementsByTagName("core").item(0).getTextContent());
            double mips = Double.parseDouble(
                hostElement.getElementsByTagName("mips").item(0).getTextContent());
            int ram = Integer.parseInt(
                hostElement.getElementsByTagName("ram").item(0).getTextContent());
            long storage = Long.parseLong(
                hostElement.getElementsByTagName("storage").item(0).getTextContent());
            long bandwidth = HOST_BANDWIDTH;

            // Host declarado com mips = 0: adota-se o dobro do MIPS da primeira VM ou,
            // sem VMs, 20 000 MIPS.
            if (mips == 0) {
                NodeList vmNodeList = hostElement.getElementsByTagName("VM");
                if (vmNodeList.getLength() > 0) {
                    Element firstVmElement = (Element) vmNodeList.item(0);
                    double vmMips = Double.parseDouble(
                        firstVmElement.getElementsByTagName("mips").item(0).getTextContent());
                    mips = vmMips * 2.0;
                } else {
                    mips = 20000.0;
                }
            }

            List<Pe> peList = createPeList(numOfCores, mips);

            List<Gpu> gpuList = createGpuList(hostElement);

            GpuProvisioner gpuProvisioner = new GpuProvisionerSimple(gpuList);

            GpuEdgeHost host = new GpuEdgeHost(
                hostIdCounter,
                new RamProvisionerSimple(ram),
                new BwProvisionerSimple(bandwidth),
                storage,
                peList,
                new VmSchedulerTimeShared(peList),
                gpuList,
                gpuProvisioner
            );

            Element locationElement = (Element) datacenterElement.getElementsByTagName("location").item(0);
            if (locationElement != null) {
                int xPos = Integer.parseInt(
                    locationElement.getElementsByTagName("x_pos").item(0).getTextContent());
                int yPos = Integer.parseInt(
                    locationElement.getElementsByTagName("y_pos").item(0).getTextContent());
                // Host de borda: tipo de local 0 e sem ponto de acesso associado (-1).
                host.setPlace(new Location(0, -1, xPos, yPos));
            }

            hostList.add(host);
            hostIdCounter++;
        }

        return hostList;
    }

    /** GPUs do host; lista vazia se o elemento {@code <gpus>} estiver ausente. */
    private List<Gpu> createGpuList(Element hostElement) {
        List<Gpu> gpuList = new ArrayList<>();

        NodeList gpusNodeList = hostElement.getElementsByTagName("gpus");
        if (gpusNodeList.getLength() == 0) {
            return gpuList;
        }

        Element gpusElement = (Element) gpusNodeList.item(0);
        NodeList gpuNodeList = gpusElement.getElementsByTagName("gpu");

        for (int i = 0; i < gpuNodeList.getLength(); i++) {
            Node gpuNode = gpuNodeList.item(i);
            Element gpuElement = (Element) gpuNode;

            String type = gpuElement.getElementsByTagName("type").item(0).getTextContent();
            int cudaCores = Integer.parseInt(
                gpuElement.getElementsByTagName("cudaCores").item(0).getTextContent());
            double gflops = Double.parseDouble(
                gpuElement.getElementsByTagName("gflops").item(0).getTextContent());
            long memory = Long.parseLong(
                gpuElement.getElementsByTagName("memory").item(0).getTextContent());
            double bandwidth = Double.parseDouble(
                gpuElement.getElementsByTagName("bandwidth").item(0).getTextContent());

            Gpu gpu = new Gpu(i, type, cudaCores, gflops, memory, bandwidth);
            gpuList.add(gpu);
        }

        return gpuList;
    }

    private List<Pe> createPeList(int numOfCores, double mips) {
        List<Pe> peList = new ArrayList<>();

        for (int i = 0; i < numOfCores; i++) {
            peList.add(new Pe(i, new PeProvisionerSimple(mips)));
        }

        return peList;
    }
}
