package gpuedgecloudsim.task_generator;

import java.util.ArrayList;
import java.util.List;

import org.apache.commons.math3.distribution.ExponentialDistribution;
import org.apache.commons.math3.random.Well19937c;

import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.task_generator.LoadGeneratorModel;
import edu.boun.edgecloudsim.utils.SimLogger;
import edu.boun.edgecloudsim.utils.SimUtils;
import edu.boun.edgecloudsim.utils.TaskProperty;

/**
 * Gera, antes da simulação, a lista de tarefas de todos os dispositivos.
 *
 * <p>Cada aplicação recebe ceil(N · p / 100) dispositivos, em que N é o número de
 * dispositivos e p o percentual de uso da aplicação, com identificadores sequenciais e
 * disjuntos entre aplicações. A chegada de tarefas de cada dispositivo é um processo de
 * Poisson de média T ou, quando configurada como periódica, ocorre a intervalos fixos T,
 * como os quadros de vídeo a 30 fps (T = 33 ms) de Rodrigues et al. (2026).</p>
 */
public class GpuLoadGeneratorModel extends LoadGeneratorModel {

    private int numberOfMobileDevices;
    /** Duração da simulação, em segundos. */
    private double simulationTime;
    private String simScenario;
    private List<GpuTaskSchedule>[] taskList;
    private int[] taskTypeOfDevices;
    private int taskIdCounter = 0;

    private class GpuTaskSchedule {
        double startTime;
        int taskType;
        int mobileDeviceId;

        GpuTaskSchedule(int _mobileDeviceId, double _startTime, int _taskType) {
            mobileDeviceId = _mobileDeviceId;
            startTime = _startTime;
            taskType = _taskType;
        }
    }

    @SuppressWarnings("unchecked")
    public GpuLoadGeneratorModel(int _numberOfMobileDevices, double _simulationTime, String _simScenario) {
        // A lista da superclasse é a que o SimManager consome.
        super.taskList = new ArrayList<>();

        this.numberOfMobileDevices = _numberOfMobileDevices;
        this.simulationTime = _simulationTime;
        this.simScenario = _simScenario;
        this.taskList = new ArrayList[SimSettings.getInstance().getTaskLookUpTable().length];
        this.taskTypeOfDevices = new int[_numberOfMobileDevices];
    }

    @Override
    public int getTaskTypeOfDevice(int deviceId) {
        return taskTypeOfDevices[deviceId];
    }

    @Override
    public void initializeModel() {
        SimLogger.printLine("Initializing GPU Load Generator Model...");

        double[][] taskLookupTable = SimSettings.getInstance().getTaskLookUpTable();
        SimLogger.printLine("DEBUG: Task lookup table loaded with " + taskLookupTable.length + " task types");

        // Índices da tabela de aplicações (SimSettings.parseApplicationsXML):
        //   [0]=usage%, [1]=prob_cloud, [2]=poisson_interarrival, [3]=active_period,
        //   [4]=idle_period, [5]=data_upload, [6]=data_download, [7]=task_length,
        //   [8]=required_core, [9..11]=vm_utilization edge/cloud/mobile,
        //   [12]=delay_sensitivity, [13]=max_delay, [14]=gpu_length, [15]=gpu_memory,
        //   [16]=gpu_input, [17]=gpu_output, [18]=periodic_arrival.

        // Os dispositivos são atribuídos às aplicações em blocos consecutivos de
        // identificadores, para que nenhum dispositivo execute duas aplicações.
        int nextAvailableDeviceId = 0;

        for (int taskIndex = 0; taskIndex < taskLookupTable.length; taskIndex++) {
            taskList[taskIndex] = new ArrayList<>();

            double[] taskConfig = taskLookupTable[taskIndex];
            double usagePercentage = taskConfig[0];
            double poissonMean = taskConfig[2];

            // O modo de chegada é definido por aplicação (<periodic_arrival>), com o
            // parâmetro global periodic_task_arrival como valor padrão.
            boolean periodicArrival =
                    SimSettings.getInstance().getPeriodicArrivalForTask(taskIndex);
            SimLogger.printLine("  App[" + taskIndex + "] chegada: "
                    + (periodicArrival ? "PERIÓDICA (" + poissonMean + "s fixo)"
                                       : "Poisson (média " + poissonMean + "s)"));

            int numberOfActiveDevices = (int) Math.ceil(
                numberOfMobileDevices * usagePercentage / 100.0
            );

            int devicesForThisTask = Math.min(numberOfActiveDevices,
                                              numberOfMobileDevices - nextAvailableDeviceId);

            SimLogger.printLine("  Task Type " + taskIndex + ": " +
                              SimSettings.getInstance().getTaskName(taskIndex) +
                              " (" + devicesForThisTask + " active devices, IDs " +
                              nextAvailableDeviceId + "-" + (nextAvailableDeviceId + devicesForThisTask - 1) + ")");

            for (int i = 0; i < devicesForThisTask; i++) {
                int actualDeviceId = nextAvailableDeviceId + i;

                if (actualDeviceId < taskTypeOfDevices.length) {
                    taskTypeOfDevices[actualDeviceId] = taskIndex;
                }

                // A distribuição recebe um gerador derivado do RNG semeado da execução;
                // sem ele, o commons-math3 usaria semente própria e a execução não
                // seria reprodutível.
                ExponentialDistribution expDist = periodicArrival ? null
                        : new ExponentialDistribution(
                                new Well19937c(SimUtils.RNG.nextLong()), poissonMean);

                // Na chegada periódica, a fase inicial de cada dispositivo é uniforme em
                // [0, T), para que os fluxos não iniciem sincronizados em t = 0.
                double taskStartTime = periodicArrival
                        ? SimUtils.RNG.nextDouble() * poissonMean
                        : expDist.sample();

                while (taskStartTime < simulationTime) {
                    taskList[taskIndex].add(new GpuTaskSchedule(
                        actualDeviceId,
                        taskStartTime,
                        taskIndex
                    ));

                    taskStartTime += periodicArrival ? poissonMean : expDist.sample();
                }
            }

            nextAvailableDeviceId += devicesForThisTask;

            SimLogger.printLine("    Generated " + taskList[taskIndex].size() +
                              " GPU tasks for this type");
            if (taskList[taskIndex].isEmpty()) {
                SimLogger.printLine("    WARNING: No tasks generated for task type " + taskIndex +
                                  " (usage=" + usagePercentage + "%, poisson=" + poissonMean + "s)");
            }
        }

        int totalTasksGenerated = 0;
        for (int i = 0; i < taskList.length; i++) {
            totalTasksGenerated += taskList[i].size();
        }
        SimLogger.printLine("DEBUG: Total GPU tasks generated: " + totalTasksGenerated);

        // Conversão para TaskProperty, o formato que o SimManager consome.
        SimLogger.printLine("Converting GPU task schedules to TaskProperty list for SimManager...");
        double[][] taskLookupTableForConversion = SimSettings.getInstance().getTaskLookUpTable();

        for (int taskIndex = 0; taskIndex < taskList.length; taskIndex++) {
            for (GpuTaskSchedule schedule : taskList[taskIndex]) {
                double[] taskConfig = taskLookupTableForConversion[schedule.taskType];

                long length = (long) taskConfig[7];
                int pesNumber = (int) taskConfig[8];
                long inputFileSize = (long) taskConfig[5];
                long outputFileSize = (long) taskConfig[6];

                TaskProperty taskProperty = new TaskProperty(
                    schedule.startTime,
                    schedule.mobileDeviceId,
                    schedule.taskType,
                    pesNumber,
                    length,
                    inputFileSize,
                    outputFileSize
                );
                super.taskList.add(taskProperty);
            }
        }
        SimLogger.printLine("Total TaskProperty entries added: " + super.taskList.size());
    }

}
