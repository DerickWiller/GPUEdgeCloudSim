package gpuedgecloudsim.core;

import edu.boun.edgecloudsim.cloud_server.CloudServerManager;
import edu.boun.edgecloudsim.cloud_server.DefaultCloudServerManager;
import edu.boun.edgecloudsim.core.ScenarioFactory;
import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.edge_client.MobileDeviceManager;
import edu.boun.edgecloudsim.edge_client.mobile_processing_unit.DefaultMobileServerManager;
import edu.boun.edgecloudsim.edge_client.mobile_processing_unit.MobileServerManager;
import edu.boun.edgecloudsim.edge_orchestrator.EdgeOrchestrator;
import edu.boun.edgecloudsim.edge_server.EdgeServerManager;
import edu.boun.edgecloudsim.mobility.MobilityModel;
import edu.boun.edgecloudsim.mobility.NomadicMobility;
import edu.boun.edgecloudsim.network.NetworkModel;
import edu.boun.edgecloudsim.task_generator.LoadGeneratorModel;

import gpuedgecloudsim.edge_client.GpuMobileDeviceManager;
import gpuedgecloudsim.edge_orchestrator.GpuEdgeOrchestrator;
import gpuedgecloudsim.edge_server.GpuEdgeServerManager;
import gpuedgecloudsim.mobility.StaticMobility;
import gpuedgecloudsim.network.GpuNetworkModel;
import gpuedgecloudsim.task_generator.GpuLoadGeneratorModel;

/**
 * Fábrica dos componentes do simulador com GPU: geração de carga, orquestração, rede e
 * servidores de borda. Nuvem, mobilidade e processamento local usam as implementações
 * padrão do EdgeCloudSim (Sonmez et al., 2018).
 */
public class GpuScenarioFactory implements ScenarioFactory {
    
    private int numOfMobileDevice;
    private double simulationTime;
    private String orchestratorPolicy;
    private String simScenario;
    
    public GpuScenarioFactory(int _numOfMobileDevice,
                              double _simulationTime,
                              String _orchestratorPolicy,
                              String _simScenario) {
        this.numOfMobileDevice = _numOfMobileDevice;
        this.simulationTime = _simulationTime;
        this.orchestratorPolicy = _orchestratorPolicy;
        this.simScenario = _simScenario;
    }
    
    @Override
    public LoadGeneratorModel getLoadGeneratorModel() {
        return new GpuLoadGeneratorModel(numOfMobileDevice, simulationTime, simScenario);
    }
    
    @Override
    public EdgeOrchestrator getEdgeOrchestrator() {
        return new GpuEdgeOrchestrator(orchestratorPolicy, simScenario);
    }
    
    @Override
    public MobilityModel getMobilityModel() {
        if (SimSettings.getInstance().isStaticMobility()) {
            return new StaticMobility(numOfMobileDevice, simulationTime);
        }
        return new NomadicMobility(numOfMobileDevice, simulationTime);
    }
    
    @Override
    public NetworkModel getNetworkModel() {
        return new GpuNetworkModel(numOfMobileDevice, simScenario);
    }
    
    @Override
    public EdgeServerManager getEdgeServerManager() {
        return new GpuEdgeServerManager();
    }
    
    @Override
    public CloudServerManager getCloudServerManager() {
        return new DefaultCloudServerManager();
    }
    
    @Override
    public MobileServerManager getMobileServerManager() {
        return new DefaultMobileServerManager();
    }
    
    @Override
    public MobileDeviceManager getMobileDeviceManager() throws Exception {
        return new GpuMobileDeviceManager();
    }
}
