# Referências analisadas

Análise estática dos ZIP enviados. Nenhum executável/DLL foi executado e nenhuma chave foi utilizada.

## client_side.zip

- `PWAdmin.ini`: perfis de servidor, paths do cliente PW, refrescamento, opções de aparência e conexão.
- `edit_roles/*.role`: documentos de personagens do Perfect World. Formato não aplicável aos personagens de Grand Chase.
- `bonusesall.txt`, `TeleportPoints.ini`, `search_history.ini`: dados auxiliares específicos do PW.
- `pwadmin_free.exe`, `libeay32.dll`, sons: não reutilizados nem redistribuídos.

## server_side.zip

- `pwadmin.conf`: porta e autenticação do agente; opções de autorização, MySQL, caminhos de backup e ligações a serviços do PW.
- `processes_config.ini`: configuração de processos, dependências e pausas; contém comandos de encerramento forçado para alguns serviços Linux. Não foram transpostos para Grand Chase.
- `instance.txt`: definições de instâncias do PW, não equivalem a mapas/instâncias controláveis no Grand Chase.
- `pwadmin`, `pwadmin.so`: binários Linux específicos do PW; não utilizados.

## Decisões para GCAdmin

- Preservar o conceito de perfis, dashboard, processos, contas e operações remotas.
- Implementar agente Windows próprio, sem dependência do licenciamento/chaves do PWAdmin.
- Não copiar chaves, senhas, endereços, dados de personagens ou código proprietário dos ZIP para o produto.
- Adaptar os comandos apenas às integrações conhecidas do Grand Chase Season 2.
- Demonstrar capacidades pendentes sem as apresentar como funcionais.
- Proteger SQL e o agente com rede privada, senha exclusiva e histórico de ações.
