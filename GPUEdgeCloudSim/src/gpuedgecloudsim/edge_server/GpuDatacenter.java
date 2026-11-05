package gpuedgecloudsim.edge_server;

import java.util.List;

import org.cloudbus.cloudsim.Cloudlet;
import org.cloudbus.cloudsim.Datacenter;
import org.cloudbus.cloudsim.DatacenterCharacteristics;
import org.cloudbus.cloudsim.Host;
import org.cloudbus.cloudsim.Storage;
import org.cloudbus.cloudsim.Vm;
import org.cloudbus.cloudsim.VmAllocationPolicy;
import org.cloudbus.cloudsim.core.CloudSim;
import org.cloudbus.cloudsim.core.CloudSimTags;
import org.cloudbus.cloudsim.core.SimEvent;

import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.utils.SimLogger;

import gpuedgecloudsim.edge_client.GpuTask;

/**
 * Datacenter que desvia para o escalonador de GPU as tarefas com gpu_length &gt; 0
 * destinadas a uma GpuEdgeVM; as demais seguem o processamento de CPU do CloudSim.
 *
 * <p>A conclusão das tarefas de GPU é verificada de duas formas: por um evento periódico
 * a cada 100 ms, sempre ativo, e, quando a conclusão por evento está habilitada, por um
 * evento avulso agendado para o instante previsto de término de cada tarefa. O segundo
 * mecanismo evita que a latência seja quantizada pelo período de 100 ms, muito superior
 * ao tempo de inferência.</p>
 */
public class GpuDatacenter extends Datacenter {

    private static final int UPDATE_GPU_PROCESSING = 1000;

    /** Verificação avulsa de conclusão; ao contrário do evento periódico, não se reagenda. */
    private static final int GPU_COMPLETION_CHECK = 1001;

    /** Período da verificação periódica de conclusão, em segundos. */
    private static final double GPU_PROCESSING_INTERVAL = 0.1;

    public GpuDatacenter(String name, DatacenterCharacteristics characteristics,
                        VmAllocationPolicy vmAllocationPolicy,
                        List<Storage> storageList, double schedulingInterval) throws Exception {
        super(name, characteristics, vmAllocationPolicy, storageList, schedulingInterval);

        SimLogger.printLine("GpuDatacenter " + name + " created (GPU-aware task processing enabled)");
    }

    @Override
    public void startEntity() {
        super.startEntity();

        schedule(getId(), GPU_PROCESSING_INTERVAL, UPDATE_GPU_PROCESSING);

        SimLogger.printLine("GpuDatacenter " + getName() + " started (periodic GPU processing scheduled)");
    }

    @Override
    public void processEvent(SimEvent ev) {
        if (ev.getTag() == CloudSimTags.CLOUDLET_SUBMIT) {
            Cloudlet cloudlet = (Cloudlet) ev.getData();

            // Toda tarefa do simulador é GpuTask; o desvio para a GPU depende de
            // gpu_length > 0, para que as tarefas de CPU consumam a CPU da VM.
            if (cloudlet instanceof GpuTask && ((GpuTask) cloudlet).getGpuLength() > 0) {
                GpuTask gpuTask = (GpuTask) cloudlet;
                gpuTask.endTransit();

                Host host = getVmAllocationPolicy().getHost(cloudlet.getVmId(), cloudlet.getUserId());
                if (host != null) {
                    Vm vm = host.getVm(cloudlet.getVmId(), cloudlet.getUserId());

                    if (vm instanceof GpuEdgeVM) {
                        GpuEdgeVM gpuEdgeVM = (GpuEdgeVM) vm;

                        SimLogger.printLine(String.format(
                            "%.3f: DEBUG GpuDatacenter: Intercepting GpuTask #%d, redirecting to GPU scheduler on VM %d",
                            CloudSim.clock(), gpuTask.getCloudletId(), gpuEdgeVM.getId()
                        ));

                        boolean success = gpuEdgeVM.submitGpuTask(gpuTask);

                        if (success) {
                            SimLogger.printLine(String.format(
                                "%.3f: DEBUG GpuDatacenter: GpuTask #%d successfully submitted to GPU scheduler",
                                CloudSim.clock(), gpuTask.getCloudletId()
                            ));

                            try {
                                gpuTask.setCloudletStatus(Cloudlet.INEXEC);
                            } catch (Exception e) {
                                SimLogger.printLine(String.format(
                                    "%.3f: WARNING GpuDatacenter: Failed to set status for GpuTask #%d: %s",
                                    CloudSim.clock(), gpuTask.getCloudletId(), e.getMessage()
                                ));
                            }

                            // Verificação agendada para o término da tarefa com a GPU
                            // exclusiva (gpuLength / capacidade). Com compartilhamento, a
                            // tarefa termina depois; o escalonador devolve o instante
                            // correto e a verificação periódica conclui a tarefa.
                            if (SimSettings.getInstance().isGpuEventDrivenCompletion()) {
                                double gflops = gpuEdgeVM.getGpu().getGflops();
                                if (gflops > 0) {
                                    double gpuTime = gpuTask.getGpuLength() / gflops;
                                    schedule(getId(), gpuTime, GPU_COMPLETION_CHECK);
                                }
                            }

                            return;
                        } else {
                            // GPU sem memória de vídeo livre: a tarefa é rejeitada por
                            // capacidade, sem redirecionamento para a CPU, de modo que toda
                            // tarefa concluída corresponda a uma inferência executada na GPU.
                            SimLogger.printLine(String.format(
                                "%.3f: GpuDatacenter: GpuTask #%d recusada pela GPU (VRAM cheia) — rejeitada por capacidade",
                                CloudSim.clock(), gpuTask.getCloudletId()
                            ));
                            SimLogger.getInstance().rejectedDueToVMCapacity(
                                gpuTask.getCloudletId(), CloudSim.clock(),
                                SimSettings.VM_TYPES.EDGE_VM.ordinal());
                            return;
                        }
                    } else {
                        SimLogger.printLine(String.format(
                            "%.3f: WARNING GpuDatacenter: GpuTask #%d assigned to non-GPU VM %d, processing as CPU task",
                            CloudSim.clock(), gpuTask.getCloudletId(), vm != null ? vm.getId() : -1
                        ));
                    }
                } else {
                    SimLogger.printLine(String.format(
                        "%.3f: ERROR GpuDatacenter: Host not found for GpuTask #%d (VM %d, User %d)",
                        CloudSim.clock(), gpuTask.getCloudletId(), cloudlet.getVmId(), cloudlet.getUserId()
                    ));
                }
            }
        }

        if (ev.getTag() == UPDATE_GPU_PROCESSING) {
            processGpuTaskUpdates();
            schedule(getId(), GPU_PROCESSING_INTERVAL, UPDATE_GPU_PROCESSING);
            return;
        }

        if (ev.getTag() == GPU_COMPLETION_CHECK) {
            processGpuTaskUpdates();
            return;
        }

        super.processEvent(ev);
    }

    /**
     * Atualiza o escalonador de GPU de todas as VMs e devolve ao dispositivo as tarefas
     * concluídas. Retorna o instante previsto da próxima conclusão.
     */
    private double processGpuTaskUpdates() {
        double currentTime = CloudSim.clock();
        double nextEventTime = Double.MAX_VALUE;

        for (Host host : getCharacteristics().getHostList()) {
            for (Vm vm : host.getVmList()) {
                if (vm instanceof GpuEdgeVM) {
                    GpuEdgeVM gpuEdgeVM = (GpuEdgeVM) vm;

                    if (gpuEdgeVM.hasGpu() && gpuEdgeVM.getGpuCloudletScheduler() != null) {
                        double nextTime = gpuEdgeVM.getGpuCloudletScheduler().updateGpuTaskProcessing(currentTime);
                        if (nextTime < nextEventTime) {
                            nextEventTime = nextTime;
                        }

                        List<GpuTask> completedTasks = gpuEdgeVM.getAndClearNewlyCompletedGpuTasks();
                        for (GpuTask gpuTask : completedTasks) {
                            sendCloudletReturn(gpuTask);
                        }
                    }
                }
            }
        }

        return nextEventTime;
    }

    private void sendCloudletReturn(GpuTask gpuTask) {
        try {
            int brokerId = gpuTask.getUserId();

            if (gpuTask.getAssociatedDatacenterId() != getId()) {
                gpuTask.setAssociatedDatacenterId(getId());
            }

            send(brokerId, 0.0, CloudSimTags.CLOUDLET_RETURN, gpuTask);

            SimLogger.printLine(String.format(
                "%.3f: DEBUG GpuDatacenter: Sent CLOUDLET_RETURN for GPU Task #%d to broker %d",
                CloudSim.clock(), gpuTask.getCloudletId(), brokerId
            ));
        } catch (Exception e) {
            SimLogger.printLine(String.format(
                "%.3f: ERROR GpuDatacenter: Failed to send CLOUDLET_RETURN for GPU Task #%d: %s",
                CloudSim.clock(), gpuTask.getCloudletId(), e.getMessage()
            ));
        }
    }
}
