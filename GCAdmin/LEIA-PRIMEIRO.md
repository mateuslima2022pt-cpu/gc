# GCAdmin · Grand Chase Season 2

Primeira versão funcional do cliente de administração e do agente Windows. Interface em português, inspirada nos fluxos enviados do PWAdmin. Não utiliza os binários, chaves, DLLs, contas ou protocolos do Perfect World.

## Abrir na tua máquina

1. Extrai esta pasta, por exemplo para `C:\GCAdmin`. Não executes dentro do ZIP.
2. Instala **Python 3.12 x64**, incluindo Python Launcher, de https://www.python.org/downloads/windows/.
3. Executa **Instalar.bat**. É necessário acesso à internet para instalar as dependências.
4. Executa **Iniciar-GCAdmin.bat**.
5. Clica em **Explorar demonstração** para conhecer as telas sem ligar ao jogo.

O cliente usa uma janela nativa via pywebview/Edge WebView2. Se o componente Windows WebView2 não estiver instalado, instala-o pelo site Microsoft. Alternativamente, abre **Iniciar-no-Navegador.bat**, que utiliza o mesmo cliente no navegador local. A demonstração é sempre identificada e não representa dados reais da VPS. Os dados de exemplo são repostos ao reiniciar o cliente.

## Ligar ao servidor real — primeiro localmente

Faz uma cópia das bases SQL antes da primeira utilização de escrita. O agente integra a estrutura Season 2 observada na conversa; ainda requer teste contra a tua instalação real.

1. No computador onde estão os executáveis do jogo, instala o mesmo pacote e as dependências.
2. Instala **Microsoft ODBC Driver 18 for SQL Server x64**. O Python x64 utiliza o driver ODBC x64; isso é independente dos drivers usados pelos executáveis antigos.
3. Executa **Iniciar-Agente.bat**, numa sessão Windows com acesso aos executáveis e ao SQL. O agente funciona numa sessão interativa; esta versão não é um serviço Windows.
4. Na primeira execução, abre-se `%LOCALAPPDATA%\GCAdmin\agent.json`. Confirma:
   - `server_root`: a pasta real dos componentes. Exemplo: `C:\GrandChaseS2\02_Codigo_Servidor`.
   - `sql.server`: a instância, por exemplo `localhost` ou `Lima`.
   - `sql.windows_auth: true`: usa a identidade Windows que iniciou o agente.
   - `backup_dir`: pasta local para os backups SQL; a conta do serviço SQL precisa de escrita nela.
   - `bind: 127.0.0.1`: acesso apenas local para o primeiro teste.
5. Fecha o Bloco de Notas. Introduz uma **senha exclusiva do agente com pelo menos 24 caracteres** quando solicitada. Não é a senha `sa`, nem uma senha do jogo. Usa a mesma senha ao reiniciar o agente para manter os perfis funcionais.
6. No GCAdmin, cria o perfil: IP `127.0.0.1`, porta `18740`, e a senha do agente.
7. Conecta. A faixa DEMONSTRAÇÃO deve desaparecer. Confere nome da máquina e contagens antes de efetuar alterações.

Podes gerar uma senha aleatória localmente: `.venv\Scripts\python.exe -m gcadmin.agent --generate-token`. Guarda-a no teu gestor de senhas; não a publiques. **Guardar senha** no cliente usa DPAPI do Windows e só pode ser recuperado pelo mesmo utilizador Windows. Perfis sem essa opção não guardam a senha.

Se preferires autenticação SQL: configura `windows_auth: false` e `user` no JSON; define `GCADMIN_SQL_PASSWORD` no ambiente do processo do agente. Não coloques a senha no JSON. Evita utilizar `sa` na instalação final; cria um login com permissões apenas para as operações que decidires ativar. O protótipo ainda usa uma única credencial administrativa do agente; não implementa contas de operadores ou papéis separados.

## Na VPS, sem expor SQL/RDP

Recomendação para esta versão: ligação privada por VPN, como Tailscale ou WireGuard, entre o teu PC e a VPS.

1. Instala o agente na VPS Windows Server 2022, com os mesmos requisitos de Python e ODBC.
2. Configura `bind` para **o IP privado específico da VPN** da VPS. O agente recusa `0.0.0.0` e listeners públicos.
3. Permite TCP 18740 no firewall **apenas a partir do IP VPN do teu computador**. Não abras essa porta publicamente.
4. No cliente, usa o IP VPN da VPS. O cliente aceita a gama privada CGNAT usada pelo Tailscale.
5. SQL continua local à VPS. O GCAdmin não necessita de expor a porta 1433.
6. Mantém a sessão Windows do agente iniciada. Pode ser bloqueada/desconectada, mas não terminada; o comportamento das consolas deve ser validado ao desconectar RDP. Não configures o agente como serviço nesta versão.

O HTTP do agente é intencionalmente limitado à rede privada/VPN, cujo túnel fornece a criptografia. O cliente também suporta HTTPS com certificado válido através de reverse proxy **configurado separadamente**. Não desativa validação TLS nem reenvia a senha em redirecionamentos.

## O que funciona nesta versão

| Área | Comportamento |
|---|---|
| Perfis | Adicionar, salvar, excluir e conectar; senha opcional via DPAPI |
| Dashboard | CPU, RAM, disco, estado dos processos, contas e indicador online |
| Contas | Pesquisa por ID, login e e-mail, consulta de personagens |
| Criação | Valida que o trigger gera só 0/1/2, nível 1, 2020 XP; caso contrário faz rollback |
| GP/cash | Define saldo total, com limites, transação e verificação de conta offline |
| Inventário | Consulta de até 150 itens de quantidade de DurationItemObjectList |
| Processos | Arranque, encerramento e reinício individual ou em sequência |
| Encerramento | Ctrl+Z e Enter na consola exata, espera por saída; nunca tskill/taskkill |
| Logs | Últimas linhas de até quatro ficheiros .log/.txt recentes por componente |
| Backup SQL | COPY_ONLY + CHECKSUM e RESTORE VERIFYONLY das bases configuradas |
| Auditoria | SQLite local ao agente, com intenção, estado e resultado das operações |

**Encerramento/reinício do GameServer bloqueado se houver contas marcadas online ou se não for possível consultar o SQL.** Sai do cliente antes. O indicador `Connecting` pode conter sessões antigas; esta versão não limpa esse campo automaticamente. Um processo em execução não prova estado Ready nem disponibilidade de rede.

O encerramento por Ctrl+Z foi validado manualmente na tua instalação, mas a implementação Python/Win32 desta versão precisa do primeiro teste supervisionado no Windows. Se falhar ou exceder 120 segundos, a sequência para e os restantes componentes ficam abertos. Código de saída indisponível é indicado sem ser apresentado como falha. A ordem mantém os serviços de suporte até o GameServer sair. O SQL Server nunca é terminado pelo agente.

## Funções apresentadas como pendentes

GM e respetivas permissões, banir/desbanir, expulsar, armazém, edição de inventário/equipamentos, edição de nível/XP, exclusão de conta/personagem, chat e avisos, eventos/rates, backup completo dos ficheiros e GPU. Não há endpoints de escrita para essas funções. Cada integração precisa das tabelas/procedimentos/protocolos exatos e de teste no pacote Grand Chase. Os botões estão desativados de forma explícita, não simulam operações reais.

Não fornece shell remoto arbitrário. Não altera o `DefaultReward.lua`, não corrige automaticamente SQL e não mexe nas rates previamente testadas. Estado de SQL e processos fica visível; dados antigos são sinalizados se o agente ficar indisponível.

## Backups e histórico

Backups ficam na VPS, em `backup_dir`. Uma cópia no mesmo disco não protege contra perda da VPS: transfere-a para outro destino. `VERIFYONLY` verifica a estrutura do backup, mas não substitui um teste de restauro. Backups das quatro bases são sequenciais, não um snapshot atómico entre bases.

`%LOCALAPPDATA%\GCAdmin\audit.sqlite` contém o histórico real. `demo-audit.sqlite` contém o histórico da demonstração. Uma entrada `pending` após falha do agente exige reconciliação; não é prova de que a operação SQL não aconteceu. O histórico está limitado a um operador autenticado por token, sem atribuição individual entre várias pessoas. As senhas de jogo e do agente não são incluídas nos pedidos auditados.

## Compilar os EXE no Windows

Executa **Compilar-Executaveis.bat** após instalar. Requer internet e Python 3.12 x64. O resultado fica em:

- `dist\GCAdmin\GCAdmin.exe` — cliente; copia a pasta inteira.
- `dist\GCAdmin-Agent\GCAdmin-Agent.exe` — agente; copia a pasta inteira.

O agente compilado continua a usar `GCADMIN_AGENT_TOKEN` e `%LOCALAPPDATA%\GCAdmin\agent.json`. Inicializa-o com `GCAdmin-Agent.exe --init`, se necessário. O atalho `Iniciar-Agente.bat` deste pacote inicia a versão Python; não inicia o EXE compilado.

Esta entrega contém o código-fonte e os scripts de compilação. **Os EXE Windows não foram compilados nem executados neste ambiente Linux.** Não renomeies um ficheiro Python para .exe. Os executáveis gerados não têm assinatura digital nesta versão.

## Testes e arquitetura

Para testes locais: `python -m unittest discover -s tests -v`.

`gcadmin/client.py`: interface desktop e gateway local, escutando apenas em 127.0.0.1, com nonce por sessão e verificação de Host/Origin. O token do agente fica no processo Python; não é enviado para o JavaScript nem armazenado no browser.

`gcadmin/agent.py`: API autenticada, limite de tamanho de pedidos e de tentativas de autenticação. `db.py`: consultas parametrizadas e transações. `processes.py`/`console_stop.py`: controlo Windows restrito aos caminhos dos componentes configurados. `service.py`: contratos e modo demo. `web/`: interface sem CDN ou dependências externas.

Consulta também `docs/REFERENCIAS.md` e `docs/VALIDACAO.md`.
