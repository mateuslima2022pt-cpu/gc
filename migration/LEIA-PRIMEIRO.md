# Preparação privada da migração Grand Chase Season 2

Esta ferramenta deve ser executada **na tua máquina Windows com o SQL Server e os ficheiros do jogo**. Não faz upload de bancos, ficheiros ou credenciais para a internet.

## Usar

1. Extrai todos os ficheiros da ferramenta para uma pasta, por exemplo `C:\Ferramenta-Migracao`.
2. Sai do cliente do jogo e encerra os sete componentes pelo GCAdmin. Confirma a operação concluída. Fecha o cliente GCAdmin para evitar um arranque durante os backups. O agente pode permanecer aberto; o SQL Server deve continuar em funcionamento.
3. Clica com o botão direito em **Preparar-Migracao-VPS.bat → Executar como administrador**.
4. Aguarda as seis etapas. Não inicies o servidor durante a preparação.
5. No fim, partilha apenas uma imagem da mensagem final. Os bancos e o pacote são privados.

Valores predefinidos:

- Pasta do servidor: `C:\GrandChaseS2\02_Codigo_Servidor`
- SQL: `localhost`, autenticação Windows da identidade que executa o script.
- Bases: **gc, Log, msg e stat**. Não utiliza Web nem billcrux.
- Destino: `C:\GrandChaseS2\PreparacaoVPS\GC-S2-Migracao-DATA-HORA-ID.zip`.

Se precisares de outros caminhos, numa consola PowerShell como administrador:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Ferramenta-Migracao\Preparar-Migracao-VPS.ps1" -ServerRoot "C:\GrandChaseS2\02_Codigo_Servidor" -SqlInstance "localhost" -OutputRoot "D:\PreparacaoVPS"
```

## O que faz

- Recusa executar com componentes do jogo ligados. Não termina processos.
- Confirma os sete executáveis, SQL local e as quatro bases ONLINE.
- Verifica uma margem de espaço em disco antes de começar. É uma estimativa; recursos em uso por outros programas ainda podem esgotar o disco.
- Faz backups integrais **COPY_ONLY e CHECKSUM**, sem compressão SQL, compatíveis com o SQL Express como origem.
- Usa a pasta de backup padrão do SQL, para herdar permissões do serviço, e executa **RESTORE VERIFYONLY**.
- Copia os `.bak` para a pasta de preparação e confere SHA256 da cópia.
- Copia a pasta do servidor, incluindo os sete componentes, DLLs, scripts Lua, DSNs e ficheiros de arranque/configuração.
- Preserva os originais. Omite logs históricos, dumps e cópias `.backup`/`.antes`.
- Mantém os valores originais das configurações, incluindo eventuais senhas. O pacote inteiro deve ser privado.
- Desativa, nas cópias, scripts com linhas `tskill` ou `taskkill /F`, acrescentando `.DESATIVADO` ao nome.
- Exporta nomes lógicos dos ficheiros SQL para o futuro restauro com `WITH MOVE`.
- Cria manifesto SHA256, ZIP e hash do ZIP. Confere cada entrada de ficheiro listada no ZIP.

Os `.bak` incluem dados, utilizadores do jogo, inventário, triggers e procedimentos corrigidos. **Logins da instância SQL, jobs do SQL Agent, drivers, bibliotecas Visual C++, regras de firewall e configuração do Windows não são transportados por esses backups.** Serão configurados na VPS.

O cliente do jogo/main.exe e o GCAdmin ficam fora deste pacote. O cliente será preparado após conhecermos o IP da VPS; o GCAdmin tem configuração própria de rede.

## Depois da transferência

Extrai o pacote na VPS e executa `Verificar-Pacote.ps1` antes de alterar os ficheiros. Os hashes garantem que os ficheiros listados foram transferidos sem alterações. Não validam o funcionamento dos executáveis nem substituem um teste de restauro.

As configurações ainda têm os IPs e a instância SQL locais. **Não executar !DBConfig.sql sobre as bases restauradas sem rever**, pois pode repor listas/objetos. Vamos configurar a VPS em conjunto depois do restauro.

A ferramenta deixa cópias adicionais dos backups na pasta de backup do SQL, indicadas na mensagem final. Não as apaga automaticamente. Se ocorrer erro, conserva a pasta incompleta com `FALHOU.txt`; não uses um ZIP dessa tentativa para migrar.

## Privacidade e validação

Não publiques o pacote em GitHub nem o envies no chat. As configurações podem conter senhas e os `.bak` contêm contas, hashes de senhas e dados de jogadores.

O script é preparado e verificado neste ambiente, mas os backups reais só podem ser executados e confirmados na tua instalação Windows/SQL Server. O primeiro teste é supervisionado: se falhar uma permissão, falta de espaço ou backup, envia apenas o erro, ocultando credenciais.

Backups de uma versão SQL mais recente não podem ser restaurados numa versão anterior. O script regista a versão de origem e avisa se for posterior a 2022; nesse caso, vamos rever a versão instalada na VPS antes de restaurar.

Versão 1.1: corrige a construção da conexão SQL no Windows PowerShell usando as palavras-chave canónicas do SqlConnectionStringBuilder.
