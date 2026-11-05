package gpuedgecloudsim.mobility;

import java.util.HashMap;
import java.util.Map;

import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import edu.boun.edgecloudsim.core.SimSettings;
import edu.boun.edgecloudsim.mobility.MobilityModel;
import edu.boun.edgecloudsim.utils.Location;

/**
 * Mobilidade estática: cada dispositivo permanece num só ponto de acesso durante toda a
 * simulação. Com mobility_static_devices_per_wlan, os dispositivos são repartidos em blocos
 * consecutivos, na ordem dos wlan_id; com mobility_static_wlan_id, todos ficam no mesmo ponto.
 */
public class StaticMobility extends MobilityModel {

    private Location[] deviceLocations;

    public StaticMobility(int _numberOfMobileDevices, double _simulationTime) {
        super(_numberOfMobileDevices, _simulationTime);
    }

    @Override
    public void initialize() {
        Map<Integer, Location> accessPoints = readAccessPoints();
        SimSettings settings = SimSettings.getInstance();
        int[] perWlan = settings.getStaticMobilityDevicesPerWlan();
        deviceLocations = new Location[numberOfMobileDevices];

        if (perWlan.length == 0) {
            Location location = accessPoint(accessPoints, settings.getStaticMobilityWlanId());
            java.util.Arrays.fill(deviceLocations, location);
            return;
        }

        int total = java.util.Arrays.stream(perWlan).sum();
        if (total != numberOfMobileDevices) {
            throw new IllegalStateException("mobility_static_devices_per_wlan soma " + total
                    + " dispositivos, mas a simulação tem " + numberOfMobileDevices);
        }
        int deviceId = 0;
        for (int wlanId = 0; wlanId < perWlan.length; wlanId++) {
            Location location = (perWlan[wlanId] > 0) ? accessPoint(accessPoints, wlanId) : null;
            for (int k = 0; k < perWlan[wlanId]; k++) {
                deviceLocations[deviceId++] = location;
            }
        }
    }

    /** Localização de cada ponto de acesso, lida dos datacenters de borda, por wlan_id. */
    private static Map<Integer, Location> readAccessPoints() {
        Map<Integer, Location> accessPoints = new HashMap<>();
        NodeList datacenters = SimSettings.getInstance().getEdgeDevicesDocument()
                                          .getElementsByTagName("datacenter");
        for (int i = 0; i < datacenters.getLength(); i++) {
            Element place = (Element) ((Element) datacenters.item(i))
                                .getElementsByTagName("location").item(0);
            int wlanId = Integer.parseInt(text(place, "wlan_id"));
            accessPoints.put(wlanId, new Location(Integer.parseInt(text(place, "attractiveness")),
                                                  wlanId,
                                                  Integer.parseInt(text(place, "x_pos")),
                                                  Integer.parseInt(text(place, "y_pos"))));
        }
        return accessPoints;
    }

    private static Location accessPoint(Map<Integer, Location> accessPoints, int wlanId) {
        Location location = accessPoints.get(wlanId);
        if (location == null) {
            throw new IllegalStateException("wlan_id=" + wlanId
                    + " não corresponde a nenhum datacenter de borda");
        }
        return location;
    }

    private static String text(Element element, String tag) {
        return element.getElementsByTagName(tag).item(0).getTextContent();
    }

    @Override
    public Location getLocation(int deviceId, double time) {
        return deviceLocations[deviceId];
    }
}
