package gpuedgecloudsim.edge_server;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedList;
import java.util.List;
import java.util.Map;

import org.cloudbus.cloudsim.Cloudlet;
import org.cloudbus.cloudsim.core.CloudSim;

import edu.boun.edgecloudsim.core.SimSettings;

import gpuedgecloudsim.edge_client.GpuTask;

/**
 * Escalonador de GPU por compartilhamento de tempo (processor sharing). Com n tarefas
 * ativas, cada uma progride à taxa C / n, em que C é a capacidade da GPU em MI/s.
 * Toda tarefa com memória de vídeo disponível é admitida; não há fila de espera nem
 * prioridade.
 *
 * <p>Simplificações: a troca de contexto não tem custo, e a disputa por banda de memória
 * de vídeo não é modelada.</p>
 */
public class GpuCloudletSchedulerTimeShared implements GpuCloudletScheduler {

    private Gpu gpu;
    private List<GpuTask> runningTasks;
    /**
     * Fila de espera nunca preenchida: a tarefa que não encontra memória de vídeo livre é
     * rejeitada, e não enfileirada.
     */
    private List<GpuTask> waitingTasks;
    private List<GpuTask> completedTasks;
    /** Concluídas desde a última consulta do GpuDatacenter, que devolve os resultados. */
    private List<GpuTask> newlyCompletedTasks;
    /** Trabalho restante por tarefa, em MI. */
    private Map<Integer, Double> taskRemainingWorkMap;
    /** Instante, em segundos, até o qual o progresso das tarefas foi contabilizado. */
    private double previousTime;

    public GpuCloudletSchedulerTimeShared() {
        this.runningTasks = new ArrayList<>();
        this.waitingTasks = new ArrayList<>();
        this.completedTasks = new ArrayList<>();
        this.newlyCompletedTasks = new LinkedList<>();
        this.taskRemainingWorkMap = new HashMap<>();
        this.previousTime = 0.0;
        this.gpu = null;
    }

    public GpuCloudletSchedulerTimeShared(Gpu gpu) {
        this();
        initialize(gpu);
    }

    @Override
    public void initialize(Gpu gpu) {
        if (gpu == null) {
            throw new IllegalArgumentException("GPU cannot be null");
        }
        this.gpu = gpu;
    }

    /** Admite a tarefa se houver memória de vídeo; caso contrário, a rejeita. */
    @Override
    public boolean submitGpuTask(GpuTask gpuTask) {
        if (gpuTask == null || gpu == null) {
            return false;
        }

        if (!gpu.allocateMemory(gpuTask.getRequiredGpuMemory())) {
            return false;
        }

        // Com conclusão por evento, o relógio do escalonador é sincronizado com o instante
        // da submissão: o progresso das tarefas ativas é contabilizado até agora, ou, com
        // a GPU ociosa, previousTime avança até agora. Sem isso, a tarefa nova receberia
        // crédito pelo intervalo anterior à sua chegada e terminaria antes do tempo.
        if (SimSettings.getInstance().isGpuEventDrivenCompletion()) {
            double now = CloudSim.clock();
            if (!runningTasks.isEmpty()) {
                updateGpuTaskProcessing(now);
            } else {
                previousTime = now;
            }
        }

        runningTasks.add(gpuTask);

        taskRemainingWorkMap.put(gpuTask.getCloudletId(), (double) gpuTask.getGpuLength());

        gpuTask.setGpuStartTime(previousTime);
        gpuTask.setExecutedGpuId(gpu.getId());

        return true;
    }

    @Override
    public boolean removeGpuTask(GpuTask gpuTask) {
        if (gpuTask == null) {
            return false;
        }

        boolean removed = runningTasks.remove(gpuTask) || waitingTasks.remove(gpuTask);

        if (removed) {
            gpu.deallocateMemory(gpuTask.getRequiredGpuMemory());
            taskRemainingWorkMap.remove(gpuTask.getCloudletId());
        }

        return removed;
    }

    /**
     * Contabiliza o progresso de todas as tarefas ativas no intervalo
     * [previousTime, currentTime], encerra as concluídas e devolve o instante previsto
     * da próxima conclusão (ou Double.MAX_VALUE, se não houver tarefa ativa).
     */
    @Override
    public double updateGpuTaskProcessing(double currentTime) {
        if (gpu == null || runningTasks.isEmpty()) {
            return Double.MAX_VALUE;
        }

        double timeSpan = currentTime - previousTime;

        if (timeSpan <= 0) {
            return Double.MAX_VALUE;
        }

        int numRunningTasks = runningTasks.size();
        double gflopsPerTask = gpu.getGflops() / numRunningTasks;

        List<GpuTask> tasksToComplete = new ArrayList<>();

        for (GpuTask task : runningTasks) {
            int taskId = task.getCloudletId();
            double remainingWork = taskRemainingWorkMap.get(taskId);

            double workDone = gflopsPerTask * timeSpan;
            double newRemainingWork = remainingWork - workDone;

            // Tolerância numérica no teste de conclusão. A verificação é agendada no
            // instante exato de término, mas o erro de arredondamento em ponto flutuante
            // pode deixar um resíduo positivo e adiar a conclusão para o evento seguinte.
            // 1e-6 MI a 22 750 MI/s corresponde a 4e-11 s, irrelevante para o resultado.
            double epsilon = 1e-6;
            if (newRemainingWork <= epsilon) {
                tasksToComplete.add(task);
            } else {
                taskRemainingWorkMap.put(taskId, newRemainingWork);
            }
        }

        for (GpuTask task : tasksToComplete) {
            finishGpuTask(task);
        }

        // Utilização binária: 100% com ao menos uma tarefa ativa, 0% caso contrário.
        if (!runningTasks.isEmpty()) {
            gpu.setUtilization(100.0);
        } else {
            gpu.setUtilization(0.0);
        }

        previousTime = currentTime;

        if (runningTasks.isEmpty()) {
            return Double.MAX_VALUE;
        }

        double minTimeToComplete = Double.MAX_VALUE;
        for (GpuTask task : runningTasks) {
            double remainingWork = taskRemainingWorkMap.get(task.getCloudletId());
            double timeToComplete = remainingWork / gflopsPerTask;
            if (timeToComplete < minTimeToComplete) {
                minTimeToComplete = timeToComplete;
            }
        }

        return currentTime + minTimeToComplete;
    }

    @Override
    public List<GpuTask> getRunningGpuTasks() {
        return new ArrayList<>(runningTasks);
    }

    @Override
    public int getRunningGpuTaskCount() {
        return runningTasks.size();
    }

    @Override
    public List<GpuTask> getWaitingGpuTasks() {
        return new ArrayList<>(waitingTasks);
    }

    @Override
    public List<GpuTask> getCompletedGpuTasks() {
        return new ArrayList<>(completedTasks);
    }

    @Override
    public double getGpuUtilization() {
        return gpu != null ? gpu.getUtilization() : 0.0;
    }

    @Override
    public boolean hasRunningTasks() {
        return !runningTasks.isEmpty();
    }

    @Override
    public Gpu getGpu() {
        return gpu;
    }

    private void finishGpuTask(GpuTask gpuTask) {
        runningTasks.remove(gpuTask);
        completedTasks.add(gpuTask);
        newlyCompletedTasks.add(gpuTask);

        gpuTask.setGpuFinishTime(previousTime);
        double executionTime = previousTime - gpuTask.getGpuStartTime();
        gpuTask.setGpuExecutionTime(executionTime);
        gpuTask.setActualGpuUtilization(gpu.getUtilization());

        try {
            gpuTask.setCloudletStatus(Cloudlet.SUCCESS);
        } catch (Exception e) {
        }

        gpu.deallocateMemory(gpuTask.getRequiredGpuMemory());
        taskRemainingWorkMap.remove(gpuTask.getCloudletId());
    }

    /** Devolve as tarefas concluídas desde a última chamada e esvazia a lista. */
    public List<GpuTask> getAndClearNewlyCompletedTasks() {
        List<GpuTask> result = new ArrayList<>(newlyCompletedTasks);
        newlyCompletedTasks.clear();
        return result;
    }
}
