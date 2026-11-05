package gpuedgecloudsim.mobility;

import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.mobility.MobilityModel;
import edu.boun.edgecloudsim.utils.Location;

/**
 * Mobilidade estática: todos os dispositivos permanecem, durante toda a simulação, no
 * ponto de acesso indicado por mobility_static_wlan_id. Isola o efeito da escolha do
 * servidor do efeito do deslocamento dos usuários.
 */
public class StaticMobility extends MobilityModel {

    private Location location;

    public StaticMobility(int _numberOfMobileDevices, double _simulationTime) {
        super(_numberOfMobileDevices, _simulationTime);
    }

    @Override
    public void initialize() {
        int wlanId = SimSettings.getInstance().getStaticMobilityWlanId();
        NodeList datacenters = SimSettings.getInstance().getEdgeDevicesDocument()
                                          .getElementsByTagName("datacenter");
        for (int i = 0; i < datacenters.getLength(); i++) {
            Element place = (Element) ((Element) datacenters.item(i))
                                .getElementsByTagName("location").item(0);
            if (Integer.parseInt(text(place, "wlan_id")) == wlanId) {
                location = new Location(Integer.parseInt(text(place, "attractiveness")), wlanId,
                                        Integer.parseInt(text(place, "x_pos")),
                                        Integer.parseInt(text(place, "y_pos")));
                return;
            }
        }
        throw new IllegalStateException("mobility_static_wlan_id=" + wlanId
                + " não corresponde a nenhum datacenter de borda");
    }

    private static String text(Element element, String tag) {
        return element.getElementsByTagName(tag).item(0).getTextContent();
    }

    @Override
    public Location getLocation(int deviceId, double time) {
        return location;
    }
}
