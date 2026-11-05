package gpuedgecloudsim.edge_client;

import org.cloudbus.cloudsim.Cloudlet;
import org.cloudbus.cloudsim.UtilizationModel;
import org.cloudbus.cloudsim.UtilizationModelFull;
import org.cloudbus.cloudsim.Vm;
import org.cloudbus.cloudsim.core.CloudSim;
import org.cloudbus.cloudsim.core.CloudSimTags;
import org.cloudbus.cloudsim.core.SimEvent;

import edu.boun.edgecloudsim.core.SimManager;
import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.edge_client.MobileDeviceManager;
import edu.boun.edgecloudsim.edge_server.EdgeHost;
import edu.boun.edgecloudsim.utils.Location;
import edu.boun.edgecloudsim.utils.SimLogger;
import edu.boun.edgecloudsim.utils.TaskProperty;

import gpuedgecloudsim.edge_client.GpuTask;
import gpuedgecloudsim.edge_server.GpuEdgeHost;

/**
 * Ciclo de vida da tarefa no dispositivo: criação da GpuTask, consulta ao orquestrador,
 * envio ao datacenter após a subida e recebimento do resultado após a descida. Falhas:
 * rejeição por capacidade, rejeição por banda na subida e falha por banda na descida.
 * Com man_enabled, a tarefa em servidor remoto passa pela MAN nos dois sentidos, um
 * evento por trecho, como no sample_app4 (Sonmez et al., 2019).
 */
public class GpuMobileDeviceManager extends MobileDeviceManager {

    /** Base das tags de evento próprias, a mesma do DefaultMobileDeviceManager. */
    private static final int BASE = 100000;
    /** A subida pela WLAN terminou no servidor local, que a repassa pela MAN. */
    private static final int REQUEST_RECEIVED_BY_EDGE_DEVICE_TO_RELAY_NEIGHBOR = BASE + 5;
    /** A descida pela MAN terminou no servidor local, que a repassa pela WLAN. */
    private static final int RESPONSE_RECEIVED_BY_EDGE_DEVICE_TO_RELAY_MOBILE_DEVICE = BASE + 7;

    private UtilizationModel cpuUtilizationModel;

    private int taskIdCounter = 0;

    public GpuMobileDeviceManager() throws Exception {
        super();
        this.cpuUtilizationModel = new UtilizationModelFull();
    }

    @Override
    public void initialize() {
        SimLogger.printLine("GpuMobileDeviceManager initialized.");
    }

    @Override
    public UtilizationModel getCpuUtilizationModel() {
        return cpuUtilizationModel;
    }

    @Override
    public void submitTask(TaskProperty taskProperty) {
        double currentTime = CloudSim.clock();

        int taskId = taskIdCounter++;

        int taskType = taskProperty.getTaskType();
        double[] appConfig = SimSettings.getInstance().getTaskLookUpTable()[taskType];

        // Índices da tabela de aplicações (SimSettings.parseApplicationsXML):
        //   [0]=usage%, [1]=prob_cloud, [2]=poisson_interarrival, [3]=active_period,
        //   [4]=idle_period, [5]=data_upload, [6]=data_download, [7]=task_length,
        //   [8]=required_core, [9]=vm_util_edge, [10]=vm_util_cloud, [11]=vm_util_mobile,
        //   [12]=delay_sensitivity, [13]=max_delay_requirement,
        //   [14]=gpu_length, [15]=gpu_memory, [16]=gpu_input_data, [17]=gpu_output_data
        long gpuLength = (appConfig.length > 14) ? (long)appConfig[14] : 0;
        long gpuMemory = (appConfig.length > 15) ? (long)appConfig[15] : 0;
        long gpuInputData = (appConfig.length > 16) ? (long)appConfig[16] : 0;
        long gpuOutputData = (appConfig.length > 17) ? (long)appConfig[17] : 0;

        GpuTask gpuTask = new GpuTask(
            taskProperty.getMobileDeviceId(),
            taskId,
            taskProperty.getLength(),
            taskProperty.getPesNumber(),
            taskProperty.getInputFileSize(),
            taskProperty.getOutputFileSize(),
            getCpuUtilizationModel(),
            getCpuUtilizationModel(),
            getCpuUtilizationModel(),
            gpuLength,
            gpuInputData,
            gpuOutputData,
            gpuMemory
        );

        Location submissionLocation = SimManager.getInstance()
                                                .getMobilityModel()
                                                .getLocation(
                                                    taskProperty.getMobileDeviceId(),
                                                    currentTime
                                                );
        gpuTask.setSubmittedLocation(submissionLocation);

        gpuTask.setUtilizationModelCpu(cpuUtilizationModel);
        gpuTask.setUtilizationModelRam(cpuUtilizationModel);
        gpuTask.setUtilizationModelBw(cpuUtilizationModel);

        gpuTask.setUserId(this.getId());
        gpuTask.setTaskType(taskType);

        // O registro no SimLogger precede a decisão de alocação, pois qualquer ramo
        // seguinte pode rejeitar a tarefa, e a rejeição exige que ela já esteja registrada.
        SimLogger.getInstance().addLog(
            gpuTask.getMobileDeviceId(),
            gpuTask.getCloudletId(),
            gpuTask.getTaskType(),
            (int)gpuTask.getCloudletLength(),
            (int)gpuTask.getCloudletFileSize(),
            (int)gpuTask.getCloudletOutputSize()
        );

        int targetDatacenterId = SimManager.getInstance()
                                           .getEdgeOrchestrator()
                                           .getDeviceToOffload(gpuTask);

        if (targetDatacenterId == SimSettings.GENERIC_EDGE_DEVICE_ID) {
            submitToEdge(gpuTask, targetDatacenterId);
        } else if (targetDatacenterId == SimSettings.CLOUD_DATACENTER_ID) {
            submitToCloud(gpuTask, targetDatacenterId);
        } else {
            SimLogger.printLine("ERROR: No suitable datacenter for GPU Task #" + taskId);

            // O orquestrador não indicou borda nem nuvem; a rejeição é atribuída à borda,
            // destino pretendido da tarefa.
            SimLogger.getInstance().rejectedDueToVMCapacity(gpuTask.getCloudletId(), currentTime,
                    SimSettings.VM_TYPES.EDGE_VM.ordinal());
        }
    }

    private void submitToEdge(GpuTask gpuTask, int datacenterId) {
        double currentTime = CloudSim.clock();

        Vm targetVm = SimManager.getInstance()
                                .getEdgeOrchestrator()
                                .getVmToOffload(gpuTask, datacenterId);

        if (targetVm == null) {
            SimLogger.printLine("ERROR: No suitable GPU VM for Task #" +
                              gpuTask.getCloudletId());

            SimLogger.getInstance().rejectedDueToVMCapacity(gpuTask.getCloudletId(), currentTime,
                    SimSettings.VM_TYPES.EDGE_VM.ordinal());
            return;
        }

        double uploadDelay = SimManager.getInstance()
                                       .getNetworkModel()
                                       .getUploadDelay(
                                           gpuTask.getMobileDeviceId(),
                                           datacenterId,
                                           gpuTask
                                       );

        // Atraso não positivo indica enlace saturado: a tarefa é descartada na entrada
        // e contabilizada como rejeição por banda.
        if (uploadDelay <= 0) {
            SimLogger.getInstance().rejectedDueToBandwidth(
                    gpuTask.getCloudletId(), currentTime,
                    SimSettings.VM_TYPES.EDGE_VM.ordinal(),
                    SimSettings.NETWORK_DELAY_TYPES.WLAN_DELAY);
            return;
        }

        gpuTask.setSubmissionTime(currentTime + uploadDelay);

        // O atraso de subida compõe o atraso de rede registrado da tarefa.
        SimLogger.getInstance().setUploadDelay(
            gpuTask.getCloudletId(), uploadDelay, SimSettings.NETWORK_DELAY_TYPES.WLAN_DELAY);

        int targetDatacenterId = targetVm.getHost().getDatacenter().getId();
        gpuTask.setAssociatedDatacenterId(targetDatacenterId);
        gpuTask.setAssociatedHostId(targetVm.getHost().getId());
        gpuTask.setAssociatedVmId(targetVm.getId());
        // O GpuDatacenter localiza o host pelo campo vmId do Cloudlet.
        gpuTask.setVmId(targetVm.getId());
        gpuTask.setRoutedThroughMan(isServedByRemoteEdge(gpuTask, targetVm));

        SimLogger.getInstance().taskStarted(gpuTask.getCloudletId(), currentTime);

        // A tarefa é enviada diretamente ao datacenter, sem passar pela lista de cloudlets
        // do DatacenterBroker, que a reenviaria sem registro no SimLogger. No caminho com
        // MAN, ela chega antes ao servidor local, que a repassa.
        if (gpuTask.isRoutedThroughMan()) {
            schedule(getId(), uploadDelay, REQUEST_RECEIVED_BY_EDGE_DEVICE_TO_RELAY_NEIGHBOR, gpuTask);
        } else {
            schedule(targetDatacenterId, uploadDelay, CloudSimTags.CLOUDLET_SUBMIT, gpuTask);
        }

        int vmType = SimSettings.VM_TYPES.EDGE_VM.ordinal();
        SimLogger.getInstance().taskAssigned(
            gpuTask.getCloudletId(),
            targetDatacenterId,
            targetVm.getHost().getId(),
            targetVm.getId(),
            vmType
        );

        SimLogger.printLine(String.format(
            "%.3f: GPU Task #%d submitted to Edge VM #%d (Upload Delay: %.3fs)",
            currentTime, gpuTask.getCloudletId(), targetVm.getId(), uploadDelay
        ));
    }

    private void submitToCloud(GpuTask gpuTask, int datacenterId) {
        double currentTime = CloudSim.clock();

        Vm targetVm = SimManager.getInstance()
                                .getEdgeOrchestrator()
                                .getVmToOffload(gpuTask, datacenterId);

        if (targetVm == null) {
            SimLogger.printLine("ERROR: No suitable cloud VM for Task #" +
                              gpuTask.getCloudletId());

            SimLogger.getInstance().rejectedDueToVMCapacity(gpuTask.getCloudletId(), currentTime,
                    SimSettings.VM_TYPES.CLOUD_VM.ordinal());
            return;
        }

        // O modelo de rede não distingue o destino: o atraso é o mesmo da WLAN, apenas
        // registrado como WAN.
        double uploadDelay = SimManager.getInstance()
                                       .getNetworkModel()
                                       .getUploadDelay(
                                           gpuTask.getMobileDeviceId(),
                                           datacenterId,
                                           gpuTask
                                       );

        gpuTask.setSubmissionTime(currentTime + uploadDelay);

        SimLogger.getInstance().setUploadDelay(
            gpuTask.getCloudletId(), uploadDelay, SimSettings.NETWORK_DELAY_TYPES.WAN_DELAY);

        gpuTask.setAssociatedDatacenterId(SimSettings.CLOUD_DATACENTER_ID);
        gpuTask.setAssociatedHostId(targetVm.getHost().getId());
        gpuTask.setAssociatedVmId(targetVm.getId());
        gpuTask.setVmId(targetVm.getId());

        SimLogger.getInstance().taskStarted(gpuTask.getCloudletId(), currentTime);

        schedule(SimSettings.CLOUD_DATACENTER_ID, uploadDelay, CloudSimTags.CLOUDLET_SUBMIT, gpuTask);

        int vmType = SimSettings.VM_TYPES.CLOUD_VM.ordinal();
        SimLogger.getInstance().taskAssigned(
            gpuTask.getCloudletId(),
            SimSettings.CLOUD_DATACENTER_ID,
            targetVm.getHost().getId(),
            targetVm.getId(),
            vmType
        );

        SimLogger.printLine(String.format(
            "%.3f: GPU Task #%d submitted to Cloud VM #%d (Upload Delay: %.3fs)",
            currentTime, gpuTask.getCloudletId(), targetVm.getId(), uploadDelay
        ));
    }

    /**
     * Verifica se a VM escolhida está em servidor distinto do que atende o ponto de acesso
     * de submissão. Cada datacenter de borda tem um ponto de acesso, identificado pelo
     * wlan_id da sua localização.
     */
    private boolean isServedByRemoteEdge(GpuTask gpuTask, Vm targetVm) {
        return SimSettings.getInstance().isManEnabled()
                && targetVm.getHost() instanceof EdgeHost
                && !GpuEdgeHost.servesAccessPoint(targetVm.getHost(), gpuTask.getSubmittedLocation());
    }

    /**
     * Repasse da subida pelo servidor local ao remoto. Com a MAN saturada, a tarefa é
     * rejeitada por banda antes de ocupar recurso de processamento.
     */
    private void relayToRemoteEdge(GpuTask gpuTask) {
        double currentTime = CloudSim.clock();
        double manDelay = SimManager.getInstance()
                                    .getNetworkModel()
                                    .getUploadDelay(SimSettings.GENERIC_EDGE_DEVICE_ID,
                                                    SimSettings.GENERIC_EDGE_DEVICE_ID,
                                                    gpuTask);
        if (manDelay <= 0) {
            SimLogger.getInstance().rejectedDueToBandwidth(
                    gpuTask.getCloudletId(), currentTime,
                    SimSettings.VM_TYPES.EDGE_VM.ordinal(),
                    SimSettings.NETWORK_DELAY_TYPES.MAN_DELAY);
            return;
        }

        gpuTask.setSubmissionTime(currentTime + manDelay);
        SimLogger.getInstance().setUploadDelay(
            gpuTask.getCloudletId(), manDelay, SimSettings.NETWORK_DELAY_TYPES.MAN_DELAY);
        schedule(gpuTask.getAssociatedDatacenterId(), manDelay, CloudSimTags.CLOUDLET_SUBMIT, gpuTask);
    }

    @Override
    public void processEvent(SimEvent ev) {
        switch (ev.getTag()) {
            case CloudSimTags.CLOUDLET_RETURN:
                processGpuTaskReturn(ev);
                break;
            case REQUEST_RECEIVED_BY_EDGE_DEVICE_TO_RELAY_NEIGHBOR:
                relayToRemoteEdge((GpuTask) ev.getData());
                break;
            case RESPONSE_RECEIVED_BY_EDGE_DEVICE_TO_RELAY_MOBILE_DEVICE: {
                GpuTask gpuTask = (GpuTask) ev.getData();
                deliverToMobileDevice(gpuTask, gpuTask.getAssociatedDatacenterId());
                break;
            }
            default:
                super.processEvent(ev);
                break;
        }
    }

    /**
     * Retorno da tarefa processada. No caminho com MAN, o resultado desce antes ao servidor
     * local; nos demais, segue direto pela WLAN ao dispositivo.
     */
    private void processGpuTaskReturn(SimEvent ev) {
        Cloudlet cloudlet = (Cloudlet) ev.getData();

        if (!(cloudlet instanceof GpuTask)) {
            super.processEvent(ev);
            return;
        }

        GpuTask gpuTask = (GpuTask) cloudlet;
        double currentTime = CloudSim.clock();

        int datacenterId = gpuTask.getAssociatedDatacenterId();
        if (datacenterId < 0) {
            datacenterId = gpuTask.getResourceId();
        }

        if (gpuTask.isRoutedThroughMan()) {
            double manDelay = SimManager.getInstance()
                                        .getNetworkModel()
                                        .getDownloadDelay(SimSettings.GENERIC_EDGE_DEVICE_ID,
                                                          SimSettings.GENERIC_EDGE_DEVICE_ID,
                                                          gpuTask);
            // MAN saturada na descida: o resultado se perde com a tarefa já processada.
            if (manDelay <= 0) {
                SimLogger.getInstance().failedDueToBandwidth(
                        gpuTask.getCloudletId(), currentTime,
                        SimSettings.NETWORK_DELAY_TYPES.MAN_DELAY);
                return;
            }
            SimLogger.getInstance().setDownloadDelay(
                gpuTask.getCloudletId(), manDelay, SimSettings.NETWORK_DELAY_TYPES.MAN_DELAY);
            schedule(getId(), manDelay, RESPONSE_RECEIVED_BY_EDGE_DEVICE_TO_RELAY_MOBILE_DEVICE, gpuTask);
            return;
        }

        deliverToMobileDevice(gpuTask, datacenterId);
    }

    /** Trecho final da descida: aplica o atraso da WLAN e encerra o registro da tarefa. */
    private void deliverToMobileDevice(GpuTask gpuTask, int datacenterId) {
        double currentTime = CloudSim.clock();

        double downloadDelay = SimManager.getInstance()
                                         .getNetworkModel()
                                         .getDownloadDelay(
                                             gpuTask.getMobileDeviceId(),
                                             datacenterId,
                                             gpuTask
                                         );

        // Enlace saturado na descida: a tarefa já foi processada e o resultado se perde.
        // Registra-se falha por banda, distinta da rejeição na entrada, pois o recurso de
        // processamento foi consumido.
        if (downloadDelay <= 0) {
            SimLogger.getInstance().failedDueToBandwidth(
                    gpuTask.getCloudletId(), currentTime,
                    SimSettings.NETWORK_DELAY_TYPES.WLAN_DELAY);
            return;
        }

        double completionTime = currentTime + downloadDelay;

        SimSettings.NETWORK_DELAY_TYPES downloadDelayType =
            (datacenterId == SimSettings.CLOUD_DATACENTER_ID)
                ? SimSettings.NETWORK_DELAY_TYPES.WAN_DELAY
                : SimSettings.NETWORK_DELAY_TYPES.WLAN_DELAY;
        SimLogger.getInstance().setDownloadDelay(
            gpuTask.getCloudletId(), downloadDelay, downloadDelayType);

        // O SimLogger exige taskExecuted antes de taskEnded.
        SimLogger.getInstance().taskExecuted(gpuTask.getCloudletId());

        SimLogger.getInstance().taskEnded(gpuTask.getCloudletId(), completionTime);

        SimLogger.printLine(String.format(
            "%.3f: GPU Task #%d completed (Exec: %.3fs, GPU: %.3fs, Download: %.3fs)",
            completionTime,
            gpuTask.getCloudletId(),
            gpuTask.getActualCPUTime(),
            gpuTask.getGpuExecutionTime(),
            downloadDelay
        ));
    }
}
