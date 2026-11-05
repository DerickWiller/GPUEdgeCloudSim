package gpuedgecloudsim.core;

import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.text.DateFormat;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;

import org.cloudbus.cloudsim.Log;
import org.cloudbus.cloudsim.core.CloudSim;

import edu.boun.edgecloudsim.core.ScenarioFactory;
import edu.boun.edgecloudsim.core.SimManager;
import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.utils.SimLogger;
import edu.boun.edgecloudsim.utils.SimUtils;

/**
 * Ponto de entrada do simulador com GPU. Executa uma simulação para cada combinação de
 * número de dispositivos, cenário e política definida no arquivo de configuração.
 */
public class GpuSimulationMain {
	
	/**
	 * @param args config.properties, edge_devices.xml, applications.xml, pasta de saída e
	 *             número da execução, que também é a semente do gerador aleatório
	 */
	public static void main(String[] args) {
		// Ponto decimal e console em UTF-8 em qualquer sistema: com o idioma pt-BR do Windows,
		// String.format usaria vírgula, e o console sairia na página de código local.
		Locale.setDefault(Locale.ROOT);
		System.setOut(new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8));
		System.setErr(new PrintStream(new FileOutputStream(FileDescriptor.err), true, StandardCharsets.UTF_8));
		Log.disable();
		
		SimLogger.enablePrintLog();
		
		int iterationNumber = 1;
		String configFile = "";
		String outputFolder = "";
		String edgeDevicesFile = "";
		String applicationsFile = "";
		
		if (args.length == 5){
			configFile = args[0];
			edgeDevicesFile = args[1];
			applicationsFile = args[2];
			outputFolder = args[3];
			iterationNumber = Integer.parseInt(args[4]);
		}
		else{
			SimLogger.printLine("========================================");
			SimLogger.printLine("GPUEdgeCloudSim");
			SimLogger.printLine("========================================");
			SimLogger.printLine("Simulation setting file, output folder and iteration number not provided!");
			SimLogger.printLine("Using default configuration files...");
			configFile = "experimentos/escala-clientes/01-cliente/config.properties";
			applicationsFile = "experimentos/escala-clientes/01-cliente/applications.xml";
			edgeDevicesFile = "experimentos/escala-clientes/01-cliente/edge_devices.xml";
			outputFolder = "resultados/teste/seed" + iterationNumber;
		}

		// A semente é aplicada antes que qualquer modelo consuma números aleatórios,
		// o que torna a execução reprodutível.
		SimUtils.seed(iterationNumber);
		SimLogger.printLine("Random seed: " + iterationNumber);

		SimSettings SS = SimSettings.getInstance();
		if(SS.initialize(configFile, edgeDevicesFile, applicationsFile) == false){
			SimLogger.printLine("ERROR: Cannot initialize simulation settings!");
			SimLogger.printLine("Please check your configuration files.");
			System.exit(1);
		}
		
		if(SS.getFileLoggingEnabled()){
			SimLogger.enableFileLog();
			SimUtils.cleanOutputFolder(outputFolder);
		}
		
		DateFormat df = new SimpleDateFormat("dd/MM/yyyy HH:mm:ss");
		Date SimulationStartDate = Calendar.getInstance().getTime();
		String now = df.format(SimulationStartDate);
		SimLogger.printLine("========================================");
		SimLogger.printLine("GPU Simulation Started");
		SimLogger.printLine("========================================");
		SimLogger.printLine("Start time: " + now);
		SimLogger.printLine("Iteration: " + iterationNumber);
		SimLogger.printLine("----------------------------------------------------------------------");

		for(int j=SS.getMinNumOfMobileDev(); j<=SS.getMaxNumOfMobileDev(); j+=SS.getMobileDevCounterSize())
		{
			for(int k=0; k<SS.getSimulationScenarios().length; k++)
			{
				for(int i=0; i<SS.getOrchestratorPolicies().length; i++)
				{
					String simScenario = SS.getSimulationScenarios()[k];
					String orchestratorPolicy = SS.getOrchestratorPolicies()[i];
					Date ScenarioStartDate = Calendar.getInstance().getTime();
					now = df.format(ScenarioStartDate);
					
					SimLogger.printLine("┌────────────────────────────────────────────────────────────┐");
					SimLogger.printLine("│ Scenario Configuration");
					SimLogger.printLine("├────────────────────────────────────────────────────────────┤");
					SimLogger.printLine("│ Scenario:         " + simScenario);
					SimLogger.printLine("│ Policy:           " + orchestratorPolicy);
					SimLogger.printLine("│ Iteration:        " + iterationNumber);
					SimLogger.printLine("│ Devices:          " + j);
					SimLogger.printLine("│ Duration:         " + SS.getSimulationTime()/60 + " minutes");
					SimLogger.printLine("│ Start time:       " + now);
					SimLogger.printLine("└────────────────────────────────────────────────────────────┘");
					
					SimLogger.getInstance().simStarted(outputFolder,"SIMRESULT_" + simScenario + "_"  + orchestratorPolicy + "_" + j + "DEVICES");
					
					try
					{
						int num_user = 2;
						Calendar calendar = Calendar.getInstance();
						boolean trace_flag = false;
				
						// Intervalo mínimo entre eventos, em segundos. O padrão do CloudSim (10 ms)
						// excede o tempo de inferência na GPU (cerca de 4 ms) e adiaria conclusões
						// para o evento seguinte; com conclusão por evento habilitada, usa-se 0,1 ms.
						double minTimeBetweenEvents = SS.isGpuEventDrivenCompletion() ? 0.0001 : 0.01;
						CloudSim.init(num_user, calendar, trace_flag, minTimeBetweenEvents);
						
						ScenarioFactory gpuFactory = new GpuScenarioFactory(j, SS.getSimulationTime(), orchestratorPolicy, simScenario);
						
						SimManager manager = new SimManager(gpuFactory, j, simScenario, orchestratorPolicy);
						
						SimLogger.printLine("Starting GPU-enabled simulation...");
						manager.startSimulation();
						SimLogger.printLine("✓ Simulation completed successfully");
					}
					catch (Exception e)
					{
						SimLogger.printLine("✗ ERROR: The simulation has been terminated due to an unexpected error");
						e.printStackTrace();
						System.exit(1);
					}
					
					Date ScenarioEndDate = Calendar.getInstance().getTime();
					now = df.format(ScenarioEndDate);
					SimLogger.printLine("Scenario finished at " + now);
					SimLogger.printLine("Duration: " + SimUtils.getTimeDifference(ScenarioStartDate, ScenarioEndDate));
					SimLogger.printLine("----------------------------------------------------------------------");
				}
			}
		}

		Date SimulationEndDate = Calendar.getInstance().getTime();
		now = df.format(SimulationEndDate);
		SimLogger.printLine("========================================");
		SimLogger.printLine("GPU Simulation Finished");
		SimLogger.printLine("========================================");
		SimLogger.printLine("End time: " + now);
		SimLogger.printLine("Total duration: " + SimUtils.getTimeDifference(SimulationStartDate, SimulationEndDate));
		SimLogger.printLine("Results saved to: " + outputFolder);
	}
}
