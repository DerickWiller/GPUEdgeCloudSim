# Modelo do simulador

O GPUEdgeCloudSim é um simulador de eventos discretos que estende o EdgeCloudSim
(Sonmez et al., 2018), construído sobre o CloudSim, com servidores de borda equipados
com GPU. Este documento descreve o que é modelado, as hipóteses adotadas e a origem de
cada parâmetro. O código-base do EdgeCloudSim fica no pacote `edu.boun.edgecloudsim` e a
extensão, no pacote `gpuedgecloudsim`, com a mesma divisão de subpacotes.

## 1. Entidades

| Entidade | Classe | Papel |
|---|---|---|
| GPU | `edge_server.Gpu` | capacidade de processamento (MI/s) e memória de vídeo (MB) |
| Servidor de borda | `edge_server.GpuEdgeHost` | host com zero ou mais GPUs |
| VM com GPU | `edge_server.GpuEdgeVM` | VM que recebe uma GPU com exclusividade |
| Escalonador de GPU | `edge_server.GpuCloudletSchedulerTimeShared` | divide a GPU entre as tarefas em execução |
| Tarefa | `edge_client.GpuTask` | quadro com parte de CPU (MI) e parte de GPU (MI, MB) |
| Gerador de carga | `task_generator.GpuLoadGeneratorModel` | chegada periódica ou de Poisson por dispositivo |
| Orquestrador | `edge_orchestrator.GpuEdgeOrchestrator` | escolhe a VM de cada tarefa |
| Rede | `network.GpuNetworkModel` | atraso de subida e descida na WLAN, na MAN e no PCIe |

## 2. Processamento na GPU

**Unidade.** O campo `gflops` do `edge_devices.xml` é uma capacidade em MI/s, e não em
operações de ponto flutuante: o nome foi herdado e a unidade é a mesma de `gpu_length`
(MI). Para a RTX 3050, 91 MI por quadro processados em 4 ms (Rodrigues et al., 2026)
dão C = 91 / 0,004 = 22 750 MI/s.

**Divisão da capacidade.** A GPU é compartilhada entre as n tarefas em execução
(*processor sharing*): cada uma progride a C / n. Com uma tarefa só, o tempo de execução
é t = L / C; com n tarefas simultâneas e de mesmo tamanho, cada uma leva n · L / C.

**Admissão por memória de vídeo.** Cada quadro reserva `gpu_memory` MB ao entrar na GPU
e os libera ao terminar. Se a memória livre não comporta o quadro, a tarefa é rejeitada
(falha por capacidade, `vm_capacity`), e não enfileirada. O número máximo de quadros em
processamento é, portanto, ⌊memória livre / gpu_memory⌋: é o buffer do servidor.

**Memória residente.** O modelo YOLO ocupa 416 MB de memória de vídeo por cliente
(Rodrigues et al., 2026). Como o simulador reserva memória por quadro e não modela
memória residente, essa parcela é descontada da memória declarada da GPU:

    memória livre = 6144 − N × 416   (MB, RTX 3050 com N clientes)

**Conclusão como evento.** O término de cada tarefa de GPU é agendado como evento no
instante calculado. Sem isso, a conclusão só seria observada no ciclo de 100 ms do
datacenter, o que quantizaria a latência em uma escala maior que os 4 ms da inferência.

## 3. Rede

O modelo de rede considera o acesso sem fio entre o dispositivo e o servidor de borda, o
barramento PCIe para as tarefas de GPU e, quando habilitada, a rede metropolitana (MAN)
entre servidores de borda:

    d_subida  = D_entrada / B_ef + [d_MAN] + t_PCIe
    d_descida = D_saída   / B_ef + [d_MAN] + t_PCIe
    t_PCIe    = 0,5 ms + 1 MB / 15,75 GB/s

O termo d_MAN existe só quando a tarefa é executada num servidor distinto do que atende
o ponto de acesso do dispositivo.

**Banda.** A WLAN tem 480 Mbps, o USB 2.0 High-Speed usado como enlace no ambiente de
Rodrigues et al. (2026), que optou por ele para isolar a variabilidade da rede sem fio.
A banda do PCIe 3.0 x16, 15,75 GB/s, segue a especificação (PCI-SIG, 2010); a latência
de 0,5 ms por travessia é um valor adotado.

**Contenção.** Com `wlan_contention_enabled=true`, a banda do ponto de acesso é dividida
igualmente entre as transmissões em curso nele, de subida e de descida. A banda de uma
transmissão é fixada no seu início e não é reavaliada enquanto ela dura, a mesma
aproximação feita pelo EdgeCloudSim. Optou-se por não usar a tabela empírica de atraso de
WLAN do EdgeCloudSim, medida em 802.11n, por ser incompatível com o enlace USB do ambiente
reproduzido.

**Buffer do enlace.** `wlan_buffer_size_kb` limita o volume pendente por ponto de acesso;
o padrão, 0, representa buffer infinito: a contenção atrasa as transmissões, mas não as
descarta. Com buffer finito, a subida recusada é registrada como rejeição por banda e a
descida recusada, como falha por banda (a tarefa já havia sido processada).

**Rede metropolitana.** Com `man_enabled=true`, cada servidor de borda fica junto ao
ponto de acesso do seu datacenter (`wlan_id` do `edge_devices.xml`), como no EdgeCloudSim
(Sonmez et al., 2018). A tarefa atribuída a uma VM de outro servidor sobe pela WLAN até o
servidor local, que a repassa pela MAN ao servidor remoto; o resultado faz o caminho
inverso. Cada troca de trecho é um evento, como no `sample_app4` do EdgeCloudSim
(Sonmez et al., 2019). A MAN é uma fila M/M/1 de servidor único por sentido, compartilhada
por todo o tráfego entre servidores:

    d_MAN = 1 / (μ − λ) + d_prop,   μ = B_MAN / (8 · S)

em que λ é a taxa de transferências pela MAN no intervalo anterior (1/s), S o tamanho
médio delas (KB), B_MAN a banda (`man_bandwidth`, em Kbps no cálculo) e d_prop o atraso de
propagação (`lan_internal_delay`, em s). λ e S são reestimados a cada 5 s a partir do
tráfego observado, o mesmo período do `sample_app4`. O primeiro intervalo assume o enlace
ocioso (λ = 0, S igual à média dos dados das aplicações ponderada pela proporção de uso);
ele termina dentro do aquecimento. Com λ ≥ μ, a fila é instável, e com d_MAN acima de
15 s, o limite do `sample_app4`, o atraso é inaceitável; nos dois casos o enlace é tratado
como saturado: na subida, a tarefa é rejeitada por banda da MAN antes de ocupar a GPU; na
descida, falha por banda da MAN com a tarefa já processada. Os dois casos aparecem no
SIMRESULT como falhas por banda da MAN, separadas das da WLAN.

Com os valores adotados (1 000 Mbps e 10 ms, os do `sample_app5` do EdgeCloudSim) e quadros
YOLO de 94 KB e 105 KB, μ ≈ 1 330/s na subida e 1 190/s na descida. Com cerca de 270
quadros/s pela MAN, a fila acrescenta cerca de 1 ms por sentido: o custo da MAN é dominado
pela propagação, cerca de 22 ms por quadro remoto entre ida e volta.

**Hipóteses da MAN.** (i) As chegadas são tratadas como Poisson em cada intervalo
(MMPP/M/1), como no EdgeCloudSim, embora a carga YOLO seja periódica; o modelo tende a
superestimar a fila. (ii) O atraso é o tempo médio no sistema da fila, e não depende do
tamanho de cada transferência. (iii) O PCIe é somado ao trecho da WLAN nos dois
sentidos, e não junto da GPU remota: o atraso total é o mesmo, muda só a ordem dos trechos
(na subida, a MAN começa t_PCIe depois; na descida, a WLAN começa t_PCIe antes). No
SIMRESULT, t_PCIe aparece no atraso da WLAN, como no caminho local. (iv) A mobilidade
não causa falha: o resultado é entregue mesmo que o dispositivo tenha mudado de ponto de
acesso durante a execução. (v) As transferências recusadas por saturação também entram na
estimativa de λ do intervalo seguinte, como no `sample_app4`: sob carga oferecida acima de
μ, o enlace permanece saturado até a carga cair, mesmo sem transmitir.

**Simplificação.** Não há enlace com a nuvem (WAN) para as tarefas de GPU, e os
parâmetros `wan_*` do `config.properties` não têm efeito sobre elas. Com
`man_enabled=false`, o padrão, todos os servidores de borda são equivalentes ao local: o
envio de um quadro a uma GPU de outro servidor não paga atraso adicional. As configurações
dos experimentos publicados usam esse padrão.

## 4. Carga

**YOLO.** Os parâmetros vêm da Tabela 2 de Rodrigues et al. (2026): 91 MI por quadro
(média da mistura de normais generalizadas), 94 KB de subida e 105 KB de descida (médias
das distribuições Johnson SU), quadros de 640 × 480 a 30 fps. A chegada é periódica, a
cada 33 ms, com fase inicial uniforme em [0, 33 ms) para que os clientes não iniciem
sincronizados. Os tamanhos são constantes e iguais às médias; a variabilidade das
distribuições não é reproduzida.

**Aplicações só de CPU.** Na carga mista, três aplicações do `sample_app1` do
EdgeCloudSim (Sonmez et al., 2018) servem de carga de fundo, com chegada de Poisson e
períodos ativo e ocioso. As proporções da carga (30% YOLO, 20%, 20% e 30%) seguem a
Tabela II de Sonmez et al. (2019).

**Aleatoriedade.** Todos os sorteios de uma execução (fase inicial e chegadas de cada
dispositivo, posição inicial e tempo de permanência em cada ponto de acesso) derivam da
semente passada na linha de comando, embaralhada por SplitMix64 (Steele; Lea; Flood, 2014)
antes de iniciar o gerador. As distribuições do commons-math3 recebem geradores derivados
dessa semente; sem isso, seriam semeadas pelo relógio. A mesma semente reproduz, portanto,
a mesma execução.

**Mobilidade estática.** Com `mobility_static_wlan_id`, todos os dispositivos ficam, durante
toda a simulação, no ponto de acesso indicado, em vez de circular entre os pontos de acesso
como na mobilidade nômade do EdgeCloudSim (Sonmez et al., 2018). Serve para isolar o efeito
da escolha do servidor do efeito do deslocamento dos usuários.

**Prazo.** `max_delay_requirement` (100 ms) é lido, mas não é imposto: nenhuma tarefa
falha por excedê-lo. A comparação com o prazo é feita na análise.

## 5. Orquestração

O orquestrador distingue dois casos pela topologia:

- **Borda heterogênea** (há VM sem GPU): tarefas de GPU só são aceitas em VMs com GPU,
  escolhidas por rodízio; na falta de GPU com memória livre, a tarefa é rejeitada. As
  tarefas de CPU podem ocupar qualquer VM, também por rodízio. A nuvem não é usada.
- **Borda homogênea** (toda VM tem GPU): a tarefa vai para a VM de menor utilização média
  de CPU e GPU.

A política configurada em `orchestrator_policies` não altera a escolha da VM; ela só
compõe o nome dos arquivos de saída.

O rodízio não considera a localização do dispositivo. Com a MAN habilitada, a fração de
quadros que a atravessam é, portanto, 1 − 1/K para um usuário que circula entre as K GPUs
estando num ponto de acesso com GPU, e 1 para quem está num ponto de acesso sem GPU. Com
chegada periódica, porém, a ordem dos quadros se repete a cada período: se o número de
clientes de GPU é múltiplo de K, cada cliente recebe sempre a mesma GPU, e a fração passa
a depender só de onde o cliente está em relação a ela.

**Seleção só local.** Com `edge_vm_selection=LOCAL`, os dois casos acima se restringem às
VMs do servidor que atende o ponto de acesso de submissão da tarefa: nenhuma tarefa
atravessa a MAN, e, sem VM local com memória livre, a tarefa é rejeitada por capacidade,
mesmo que outro servidor esteja ocioso. O padrão, `AUTO`, é o critério da topologia.

## 6. Infraestrutura

- **Densidade de GPU:** 14 servidores de borda com 8 VMs de 2 núcleos a 10 000 MIPS e
  nuvem com 4 VMs de 100 000 MIPS e 100 ms de atraso (Toczé et al., 2020, Tabela 5).
  Os K primeiros servidores recebem uma RTX 3050, atribuída a uma de suas VMs.
- **Escala de clientes:** um servidor com uma RTX 3050 e uma VM que a utiliza, como no
  ambiente de Rodrigues et al. (2026).
- **Dois servidores:** dois servidores iguais aos da densidade, ambos com uma RTX 3050, e
  todos os clientes fixos no ponto de acesso do primeiro, com a MAN habilitada. Compara o
  rodízio entre as duas GPUs, que paga a MAN em metade dos quadros, com a seleção só local.

## 7. Parâmetros sem fonte externa

| Parâmetro | Valor | Justificativa |
|---|---|---|
| `gpu_memory` (memória de trabalho por quadro) | 20 MB | compatível com o maior tensor de ativação de uma inferência YOLO a 416 × 416 em FP32 (21,1 MB); a 640 × 480 seriam 37,5 MB |
| latência do PCIe por travessia | 0,5 ms | valor adotado |
| `wlan_buffer_size_kb` | 0 (infinito) | sem medida do buffer do enlace USB |
| `man_bandwidth` | 1 000 Mbps | valor do `sample_app5` do EdgeCloudSim (Sonmez et al., 2018) |
| `lan_internal_delay` (propagação na MAN) | 10 ms | valor do `sample_app5` do EdgeCloudSim; o `sample_app4` usa 5 ms |
| intervalo de reestimação da MAN | 5 s | período do `sample_app4` do EdgeCloudSim (Sonmez et al., 2019) |

O valor de `gpu_memory` define o buffer do servidor e, sob saturação, a taxa de perda.
Há também uma hipótese associada: assume-se que os 416 MB por cliente medidos por
Rodrigues et al. (2026) não incluem a memória de trabalho da inferência. Se a incluíssem,
a memória por quadro estaria sendo cobrada duas vezes.

## 8. Limitações conhecidas

- **Utilização da GPU binária.** A utilização registrada é 100% com qualquer tarefa em
  execução e 0% sem nenhuma. O registro `VM_LOAD` do SIMRESULT, amostrado a cada 6 s,
  mede a média entre CPU e essa utilização binária por host, e não a ocupação real da GPU;
  a ocupação é obtida analiticamente pelos validadores.
- **Truncamento do CloudSim.** O CloudSim trunca o trabalho restante de cada tarefa de CPU
  para um número inteiro de MI, o que a conclui até 1 MI antes do total (0,1 ms a
  10 000 MIPS). As tarefas de GPU não passam por esse cálculo.
- **Isolamento entre aplicações.** O modelo não representa disputa de barramento, cache ou
  memória do host entre CPU e GPU; o isolamento observado entre as classes de aplicação é
  consequência dessa simplificação.

## Referências

- PCI-SIG. *PCI Express Base Specification, Revision 3.0*, 2010.
- Rodrigues, K. C.; Cardoso, K. V.; Correa, S. L. *Characterization of Mobile Augmented
  Reality Tasks Supported by Edge Computing Resources*. SBRC, 2026.
- Sonmez, C.; Ozgovde, A.; Ersoy, C. *EdgeCloudSim: An environment for performance
  evaluation of edge computing systems*. Transactions on Emerging Telecommunications
  Technologies, 2018.
- Sonmez, C.; Ozgovde, A.; Ersoy, C. *Fuzzy Workload Orchestration for Edge Computing*.
  IEEE Transactions on Network and Service Management, 2019.
- Steele, G. L.; Lea, D.; Flood, C. H. *Fast splittable pseudorandom number generators*.
  OOPSLA, 2014.
- Toczé, K.; Lindqvist, J.; Nadjm-Tehrani, S. *Characterization and modeling of an edge
  computing mixed reality workload*. Journal of Cloud Computing, 2020.
