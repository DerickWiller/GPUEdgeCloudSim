#!/usr/bin/env python3
"""Gera as configurações dos pontos dos experimentos.

Cada ponto é uma pasta com os três arquivos lidos pelo simulador: config.properties,
edge_devices.xml e applications.xml. Dentro de um experimento os pontos diferem em uma
única variável, e por isso são produzidos a partir de um mesmo modelo:

    densidade-gpu     K servidores com GPU entre 14, com 9 clientes YOLO fixos;
    escala-clientes   N clientes YOLO sobre uma única GPU;
    dois-servidores   N clientes YOLO num ponto de acesso, com uma segunda GPU
                      alcançável pela MAN;
    cameras-fixas     câmeras YOLO fixas em quatro pontos de acesso com GPU, com
                      h câmeras no ponto mais carregado.

Os arquivos gerados são derivados: alterações devem ser feitas neste script.

Uso:
    python3 experimentos/gerar_configs.py
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent / "analise"))
from config import pasta_do_ponto  # noqa: E402

# --- Carga YOLO e GPU (Rodrigues et al., 2026) -----------------------------------
GFLOPS = 22750           # capacidade da RTX 3050, em MI/s: 91 MI / 4 ms
MI_POR_QUADRO = 91       # média da mistura de normais generalizadas da Tabela 2
VRAM_FISICA = 6144       # MB da RTX 3050
VRAM_POR_CLIENTE = 416   # MB do modelo YOLO residente, por cliente
MEM_POR_QUADRO = 20      # MB de memória de trabalho por quadro em processamento

# --- Pontos de cada experimento ---------------------------------------------------
DENSIDADE_K = [1, 2, 3, 7, 14]
DENSIDADE_CLIENTES_YOLO = 9          # 30% de 30 dispositivos
ESCALA_N = [1, 4, 6, 8, 9, 10, 12, 14]
DOIS_SERVIDORES_N = ESCALA_N
# Com 10 ou mais clientes num ponto de acesso, a WLAN (480 Mbps) satura antes das duas GPUs
# no rodízio (480 / 48,24 Mbps por cliente = 9,95): esses pontos só existem na política local.
DOIS_SERVIDORES_N_RODIZIO = [n for n in ESCALA_N if n <= 9]
# Câmeras fixas: h câmeras no ponto quente (ponto de acesso 0) e 2, 1 e 1 nos demais. O
# máximo de 9 por ponto mantém a WLAN abaixo da saturação (9,95), e o total, até 13, mantém
# memória livre em cada GPU (6144 − 13 × 416 = 736 MB).
CAMERAS_H = [2, 4, 6, 8, 9]
CAMERAS_DEMAIS = [2, 1, 1]
CAMERAS_POLITICAS = {
    "local": ("LOCAL", "só a GPU do próprio ponto de acesso"),
    "rodizio": ("AUTO", "rodízio entre as quatro GPUs"),
    "local-primeiro": ("LOCAL_FIRST", "GPU de menor tempo estimado, com a MAN"),
}


def pasta_densidade(k: int) -> Path:
    return RAIZ / "densidade-gpu" / pasta_do_ponto("densidade", k)


def pasta_escala(n: int) -> Path:
    return RAIZ / "escala-clientes" / pasta_do_ponto("escala", n)


def pasta_dois_servidores(politica: str, n: int) -> Path:
    return RAIZ / "dois-servidores" / politica / pasta_do_ponto("escala", n)


def pasta_cameras(politica: str, h: int) -> Path:
    return RAIZ / "cameras-fixas" / politica / f"{h:02d}-no-ponto-quente"


def vram_livre(clientes_yolo: int) -> int:
    """Memória de vídeo disponível para os quadros, em MB.

    O motor reserva memória por quadro e não modela a memória residente do modelo;
    por isso a parcela residente é descontada da capacidade declarada da GPU:
    memory = 6144 − N × 416.
    """
    return VRAM_FISICA - clientes_yolo * VRAM_POR_CLIENTE


# =============================================================================
# config.properties
# =============================================================================

def config_properties(titulo: str, dispositivos: int, rede_nuvem: dict,
                      chegada_periodica_global: bool, extra: str = "",
                      duracao_min: int = 60, aquecimento_min: int = 5,
                      man_banda_mbps: float = 1000, lan_atraso_s: float = 0.01) -> str:
    chegada = ("""
# Chegada periódica para todas as aplicações: o quadro é emitido a cada
# poisson_interarrival segundos, com fase inicial uniforme por dispositivo.
periodic_task_arrival=true
""" if chegada_periodica_global else "") + extra

    return f"""# {titulo}
# Arquivo gerado por experimentos/gerar_configs.py.

# Duração, em minutos: {duracao_min} min simulados, dos quais os {aquecimento_min} primeiros são descartados
# como aquecimento. Os intervalos de amostragem também estão em minutos (0,1 min = 6 s).
simulation_time={duracao_min}
warm_up_period={aquecimento_min}
vm_load_check_interval=0.1
location_check_interval=0.1
ap_delay_check_interval=0.1

# O registro por tarefa (deep log) é ligado por execucao/rodar_deeplog.sh.
file_log_enabled=true
deep_file_log_enabled=false

min_number_of_mobile_devices={dispositivos}
max_number_of_mobile_devices={dispositivos}
mobile_device_counter_size={dispositivos}

# Rede, em segundos e Mbps. A WLAN de 480 Mbps corresponde ao USB 2.0 High-Speed,
# enlace do ambiente experimental de Rodrigues et al. (2026). Os demais valores
# são os do EdgeCloudSim (Sonmez et al., 2018); man_bandwidth e lan_internal_delay
# são os do sample_app5. A MAN só é atravessada com man_enabled=true; o modelo de
# rede GPU não usa WAN nem GSM.
wan_propagation_delay={rede_nuvem['wan_propagation_delay']}
gsm_propagation_delay=0.16
lan_internal_delay={lan_atraso_s:g}
wlan_bandwidth=480
man_bandwidth={man_banda_mbps:g}
wan_bandwidth=50
gsm_bandwidth=20

# A banda de cada ponto de acesso é repartida entre as transmissões simultâneas.
wlan_contention_enabled=true

# A conclusão das tarefas de GPU é tratada como evento; sem isso, ela só seria
# observada no ciclo de 100 ms do datacenter, o que quantiza a latência.
gpu_event_driven_completion=true
{chegada}
# {rede_nuvem['comentario']}
number_of_host_on_cloud_datacenter=1
number_of_vm_on_cloud_host={rede_nuvem['number_of_vm_on_cloud_host']}
core_for_cloud_vm=4
mips_for_cloud_vm={rede_nuvem['mips_for_cloud_vm']}
ram_for_cloud_vm=16000
storage_for_cloud_vm=250000

# Sem processamento local no dispositivo móvel.
core_for_mobile_vm=0
mips_for_mobile_vm=0
ram_for_mobile_vm=0
storage_for_mobile_vm=0

# Rótulos que compõem o nome dos arquivos SIMRESULT; a escolha da VM pelo
# orquestrador GPU não depende deles.
orchestrator_policies=NEXT_FIT
simulation_scenarios=EQUAL_CAPACITY

# Tempo médio de permanência em um ponto de acesso, em segundos, por nível de
# atratividade (Sonmez et al., 2018).
attractiveness_L1_mean_waiting_time=300
attractiveness_L2_mean_waiting_time=200
attractiveness_L3_mean_waiting_time=100
"""


# =============================================================================
# applications.xml
# =============================================================================

def app_yolo(uso_pct: int, periodica_na_app: bool) -> str:
    chegada = ("""
        <!-- Chegada periódica só para esta aplicação; as demais seguem Poisson. -->
        <periodic_arrival>true</periodic_arrival>""" if periodica_na_app else "")
    return f"""    <!-- Detecção de objetos YOLO sobre quadros de 640x480 a 30 fps
         (Rodrigues et al., 2026, Tabela 2). -->
    <application name="YOLO_DETECTION">
        <usage_percentage>{uso_pct}</usage_percentage>
        <!-- O orquestrador GPU não amostra este campo. -->
        <prob_cloud_selection>0</prob_cloud_selection>
        <delay_sensitivity>0.95</delay_sensitivity>
        <!-- Orçamento de 100 ms da realidade aumentada. Não é imposto pelo motor:
             nenhuma tarefa falha por excedê-lo; a comparação é feita na análise. -->
        <max_delay_requirement>0.1</max_delay_requirement>
        <!-- Intervalo entre quadros, em s. Com chegada periódica, é o período fixo
             de 33 ms, e não a média de um processo de Poisson. -->
        <poisson_interarrival>0.033</poisson_interarrival>
        <!-- Fluxo contínuo: ativo durante toda a simulação, em s. -->
        <active_period>3600</active_period>
        <idle_period>1</idle_period>
        <!-- Pré e pós-processamento em CPU, em MI. -->
        <task_length>50</task_length>
        <required_core>1</required_core>
        <!-- Quadro enviado e quadro anotado, em KB: médias das distribuições
             Johnson SU de subida (94,20 KB) e de descida (104,56 KB). -->
        <data_upload>94</data_upload>
        <data_download>105</data_download>
        <!-- Inferência, em MI: 91 MI / 22 750 MI/s = 4 ms na RTX 3050. -->
        <gpu_length>91</gpu_length>
        <!-- Memória de trabalho por quadro, em MB. Valor adotado sem fonte externa;
             os 416 MB por cliente do modelo residente são descontados da GPU em
             edge_devices.xml. Junto com a memória livre, define quantos quadros
             podem estar em processamento. -->
        <gpu_memory>{MEM_POR_QUADRO}</gpu_memory>{chegada}
        <!-- Volume transferido pelo barramento PCIe, em MB. -->
        <gpu_input_data>1</gpu_input_data>
        <gpu_output_data>1</gpu_output_data>
        <vm_utilization_on_edge>0</vm_utilization_on_edge>
        <vm_utilization_on_cloud>0</vm_utilization_on_cloud>
        <vm_utilization_on_mobile>0</vm_utilization_on_mobile>
    </application>
"""


def app_cpu(nome, uso, nuvem, chegada, ativo, ocioso, mi, subida, descida, vm_edge, vm_cloud):
    return f"""    <application name="{nome}">
        <usage_percentage>{uso}</usage_percentage>
        <prob_cloud_selection>{nuvem}</prob_cloud_selection>
        <delay_sensitivity>0</delay_sensitivity>
        <poisson_interarrival>{chegada}</poisson_interarrival>
        <active_period>{ativo}</active_period>
        <idle_period>{ocioso}</idle_period>
        <task_length>{mi}</task_length>
        <required_core>1</required_core>
        <data_upload>{subida}</data_upload>
        <data_download>{descida}</data_download>
        <vm_utilization_on_edge>{vm_edge}</vm_utilization_on_edge>
        <vm_utilization_on_cloud>{vm_cloud}</vm_utilization_on_cloud>
        <vm_utilization_on_mobile>0</vm_utilization_on_mobile>
    </application>
"""


def applications_misto() -> str:
    return f"""<?xml version='1.0' encoding='utf-8'?>
<!--
  Carga mista: 30% dos dispositivos executam YOLO na GPU e 70% executam três
  aplicações só de CPU. As proporções seguem a Tabela II de Sonmez et al. (2019);
  os parâmetros das aplicações de CPU são os do sample_app1 do EdgeCloudSim
  (Sonmez et al., 2018), com tempos em s, tamanho em MI e dados em KB.
  Arquivo gerado por experimentos/gerar_configs.py.
-->
<applications>

{app_yolo(30, periodica_na_app=True)}
    <!-- Aplicações só de CPU, com chegada de Poisson. -->
{app_cpu("HEALTH_APP", 20, 20, 30, 10, 20, 400, 1250, 20, 5, 0.5)}
{app_cpu("HEAVY_COMP_APP", 20, 40, 60, 60, 60, 3000, 2500, 250, 30, 3)}
{app_cpu("INFOTAINMENT_APP", 30, 15, 7, 15, 45, 750, 25, 2000, 10, 1)}
</applications>
"""


def applications_yolo() -> str:
    return f"""<?xml version='1.0' encoding='utf-8'?>
<!--
  Carga exclusiva de YOLO: todos os dispositivos são clientes de detecção de objetos.
  Arquivo gerado por experimentos/gerar_configs.py.
-->
<applications>

{app_yolo(100, periodica_na_app=False)}
</applications>
"""


# =============================================================================
# edge_devices.xml
# =============================================================================

def bloco_gpu(memoria: int, recuo: str) -> str:
    return f"""{recuo}<gpus>
{recuo}\t<gpu>
{recuo}\t\t<type>NVIDIA_RTX_3050</type>
{recuo}\t\t<cudaCores>2048</cudaCores>
{recuo}\t\t<!-- Capacidade em MI/s: 91 MI / 4 ms. -->
{recuo}\t\t<gflops>{GFLOPS}</gflops>
{recuo}\t\t<!-- Memória livre para quadros, em MB: 6144 − N × 416. -->
{recuo}\t\t<memory>{memoria}</memory>
{recuo}\t\t<!-- Banda de memória, em GB/s; não entra no cálculo do tempo de execução. -->
{recuo}\t\t<bandwidth>224</bandwidth>
{recuo}\t</gpu>
{recuo}</gpus>
"""


def datacenter(indice: int, x: int, atratividade: int, host: str) -> str:
    return f"""\t<datacenter arch="x86" os="Linux" vmm="Xen">
\t\t<costPerBw>0.1</costPerBw>
\t\t<costPerSec>3.0</costPerSec>
\t\t<costPerMem>0.05</costPerMem>
\t\t<costPerStorage>0.1</costPerStorage>
\t\t<location>
\t\t\t<x_pos>{x}</x_pos>
\t\t\t<y_pos>0</y_pos>
\t\t\t<wlan_id>{indice}</wlan_id>
\t\t\t<attractiveness>{atratividade}</attractiveness>
\t\t</location>
\t\t<hosts>
{host}\t\t</hosts>
\t</datacenter>
"""


def host_borda(com_gpu: bool, memoria: int) -> str:
    """Servidor de borda da densidade (Toczé et al., 2020, Tabela 5): 8 VMs de 2 núcleos a
    10 000 MIPS; com GPU, a RTX 3050 fica com a primeira VM."""
    vm = ('<VM vmm="Xen" requiresGpu="{g}"><core>2</core><mips>10000</mips>'
          '<ram>4096</ram><storage>100000</storage></VM>')
    vms = [vm.format(g="true" if (com_gpu and j == 0) else "false") for j in range(8)]
    return ("\t\t\t<host>\n"
            "\t\t\t\t<core>16</core>\n"
            "\t\t\t\t<mips>0</mips>\n"
            "\t\t\t\t<ram>65536</ram>\n"
            "\t\t\t\t<storage>2000000</storage>\n"
            + (bloco_gpu(memoria, "\t\t\t\t") if com_gpu else "")
            + "\t\t\t\t<VMs>\n"
            + "".join(f"\t\t\t\t\t{v}\n" for v in vms)
            + "\t\t\t\t</VMs>\n"
            "\t\t\t</host>\n")


def edge_devices_densidade(k: int) -> str:
    """Catorze servidores de borda (Toczé et al., 2020, Tabela 5); os K primeiros têm GPU."""
    memoria = vram_livre(DENSIDADE_CLIENTES_YOLO)
    dcs = []
    for i in range(14):
        host = host_borda(i < k, memoria)
        # Pontos de acesso espaçados de 400 unidades no eixo x; atratividade 2, 1, 1 em ciclo.
        dcs.append(datacenter(i, 200 + 400 * i, 2 if i % 3 == 0 else 1, host))

    return f"""<?xml version='1.0' encoding='utf-8'?>
<!--
  Catorze servidores de borda com 8 VMs de 2 núcleos e 10 000 MIPS cada
  (Toczé et al., 2020, Tabela 5). Os {k} primeiros têm uma RTX 3050, atribuída
  com exclusividade à primeira VM do servidor; as tarefas YOLO só são aceitas
  nessas VMs, e as de CPU, em qualquer uma das 112.
  A memória livre de cada GPU desconta o modelo residente dos 9 clientes YOLO,
  pois a distribuição circular envia quadros de todos eles a todas as GPUs:
  6144 − 9 × 416 = {memoria} MB.
  Com mips = 0, o MIPS do núcleo físico é derivado das VMs alocadas.
  Arquivo gerado por experimentos/gerar_configs.py.
-->
<edge_devices>

{"".join(dcs)}
</edge_devices>
"""


def edge_devices_escala(n: int) -> str:
    """Um servidor de borda com uma RTX 3050, como no ambiente de Rodrigues et al. (2026)."""
    memoria = vram_livre(n)
    host = ("\t\t\t<host>\n"
            "\t\t\t\t<core>4</core>\n"
            "\t\t\t\t<mips>0</mips>\n"
            "\t\t\t\t<ram>16000</ram>\n"
            "\t\t\t\t<storage>250000</storage>\n"
            + bloco_gpu(memoria, "\t\t\t\t")
            + "\t\t\t\t<VMs>\n"
            '\t\t\t\t\t<VM vmm="Xen" requiresGpu="true"><core>4</core><mips>10000</mips>'
            '<ram>8192</ram><storage>100000</storage></VM>\n'
            "\t\t\t\t</VMs>\n"
            "\t\t\t</host>\n")
    return f"""<?xml version='1.0' encoding='utf-8'?>
<!--
  Um servidor de borda com uma RTX 3050 e uma VM que a utiliza com exclusividade.
  Memória livre da GPU: 6144 − {n} × 416 = {memoria} MB, o que limita a
  {memoria // MEM_POR_QUADRO} o número de quadros em processamento simultâneo.
  Arquivo gerado por experimentos/gerar_configs.py.
-->
<edge_devices>

{datacenter(0, 200, 2, host)}
</edge_devices>
"""


def edge_devices_dois_servidores(n: int) -> str:
    """Dois servidores de borda iguais aos da densidade, ambos com uma RTX 3050."""
    memoria = vram_livre(n)
    dcs = [datacenter(i, 200 + 400 * i, 2, host_borda(True, memoria)) for i in range(2)]
    return f"""<?xml version='1.0' encoding='utf-8'?>
<!--
  Dois servidores de borda com 8 VMs de 2 núcleos e 10 000 MIPS cada, como na
  densidade de GPU (Toczé et al., 2020, Tabela 5); ambos têm uma RTX 3050,
  atribuída à primeira VM. Os clientes ficam todos no ponto de acesso do
  primeiro servidor; o segundo só é alcançado pela MAN.
  Memória livre de cada GPU: 6144 − {n} × 416 = {memoria} MB, pois o rodízio
  envia quadros de todos os clientes às duas GPUs.
  Arquivo gerado por experimentos/gerar_configs.py.
-->
<edge_devices>

{"".join(dcs)}
</edge_devices>
"""


def edge_devices_cameras(h: int) -> str:
    """Quatro servidores de borda iguais aos da densidade, cada um com uma RTX 3050."""
    total = h + sum(CAMERAS_DEMAIS)
    memoria = vram_livre(total)
    dcs = [datacenter(i, 200 + 400 * i, 2, host_borda(True, memoria)) for i in range(4)]
    return f"""<?xml version='1.0' encoding='utf-8'?>
<!--
  Quatro servidores de borda com 8 VMs de 2 núcleos e 10 000 MIPS cada, como na
  densidade de GPU (Toczé et al., 2020, Tabela 5), um por ponto de acesso, cada
  um com uma RTX 3050 atribuída à primeira VM. As câmeras ficam fixas: {h} no
  ponto de acesso 0 e {", ".join(map(str, CAMERAS_DEMAIS))} nos demais.
  Memória livre de cada GPU: 6144 − {total} × 416 = {memoria} MB. Adota-se o mesmo
  valor nas três políticas: no rodízio e na escolha pelo menor tempo estimado,
  qualquer câmera pode ser atendida por qualquer GPU.
  Arquivo gerado por experimentos/gerar_configs.py.
-->
<edge_devices>

{"".join(dcs)}
</edge_devices>
"""


# =============================================================================

def escrever(pasta: Path, config: str, apps: str, edge: str) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "config.properties").write_text(config, encoding="utf-8")
    (pasta / "applications.xml").write_text(apps, encoding="utf-8")
    (pasta / "edge_devices.xml").write_text(edge, encoding="utf-8")
    print(pasta.relative_to(RAIZ))


NUVEM_DENSIDADE = {"comentario": "Nuvem: 4 VMs de 100 000 MIPS e atraso de 100 ms "
                                 "(Toczé et al., 2020, Tabela 5).",
                   "wan_propagation_delay": 0.1,
                   "number_of_vm_on_cloud_host": 4, "mips_for_cloud_vm": 100000}
NUVEM_ESCALA = {"comentario": "Nuvem: valores de referência do EdgeCloudSim.",
                "wan_propagation_delay": 0.15,
                "number_of_vm_on_cloud_host": 2, "mips_for_cloud_vm": 50000}


def main() -> None:
    nuvem_densidade, nuvem_escala = NUVEM_DENSIDADE, NUVEM_ESCALA

    for k in DENSIDADE_K:
        escrever(pasta_densidade(k),
                 config_properties(f"Densidade de GPU: {k} de 14 servidores com GPU, "
                                   "30 dispositivos, carga mista.",
                                   30, nuvem_densidade, chegada_periodica_global=False),
                 applications_misto(),
                 edge_devices_densidade(k))

    for n in ESCALA_N:
        escrever(pasta_escala(n),
                 config_properties(f"Escala de clientes: {n} cliente{'s' if n > 1 else ''} "
                                   "YOLO sobre uma GPU.",
                                   n, nuvem_escala, chegada_periodica_global=True),
                 applications_yolo(),
                 edge_devices_escala(n))

    # Todos os clientes fixos no ponto de acesso 0, com a MAN ligada. No rodízio, a GPU
    # segue o critério da borda heterogênea; na política local, só a GPU do servidor 0.
    extra = """
# Rede metropolitana entre os servidores e clientes fixos no ponto de acesso 0.
man_enabled=true
mobility_static_wlan_id=0
"""
    politicas = {
        "rodizio": (DOIS_SERVIDORES_N_RODIZIO, "rodízio entre as duas GPUs", ""),
        "local": (DOIS_SERVIDORES_N, "só a GPU local",
                  "\n# Só as VMs do servidor do ponto de acesso do dispositivo.\nedge_vm_selection=LOCAL\n"),
    }
    for politica, (pontos, rotulo, chave) in politicas.items():
        for n in pontos:
            escrever(pasta_dois_servidores(politica, n),
                     config_properties(f"Dois servidores: {n} cliente{'s' if n > 1 else ''} "
                                       f"YOLO num ponto de acesso, {rotulo}.",
                                       n, nuvem_escala, chegada_periodica_global=True,
                                       extra=extra + chave),
                     applications_yolo(),
                     edge_devices_dois_servidores(n))

    # Câmeras fixas em quatro pontos de acesso, com a MAN ligada; só a política varia.
    for politica, (selecao, rotulo) in CAMERAS_POLITICAS.items():
        for h in CAMERAS_H:
            por_ponto = [h] + CAMERAS_DEMAIS
            extra = f"""
# Rede metropolitana entre os servidores; câmeras fixas, por ponto de acesso (wlan_id 0 a 3).
man_enabled=true
mobility_static_devices_per_wlan={",".join(map(str, por_ponto))}

# Escolha da GPU: {rotulo}.
edge_vm_selection={selecao}
"""
            escrever(pasta_cameras(politica, h),
                     config_properties(f"Câmeras fixas: {h} câmeras YOLO no ponto quente e "
                                       f"{sum(CAMERAS_DEMAIS)} nos demais, {rotulo}.",
                                       sum(por_ponto), nuvem_escala,
                                       chegada_periodica_global=True, extra=extra),
                     applications_yolo(),
                     edge_devices_cameras(h))


if __name__ == "__main__":
    main()
