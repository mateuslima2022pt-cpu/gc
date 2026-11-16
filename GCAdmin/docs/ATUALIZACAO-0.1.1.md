# Atualização 0.1.1

Corrige a falha ao abrir uma conta em bases Season 2 sem a coluna `Characters.CharName`.

A consulta usa apenas CharType, Promotion, Level, Exp, Win e Lose. O campo opcional `name` da API fica nulo; os nomes Elesis, Lire, Arme, etc. continuam a ser identificados por CharType. Não cria colunas, não muda tabelas e não altera dados do jogo.

## Aplicar na instalação existente

1. Fecha o cliente GCAdmin.
2. Na consola do **agente GCAdmin**, prime Ctrl+C. Não precisas de fechar os componentes do jogo nem o SQL Server.
3. No ZIP completo, abre `GCAdmin/gcadmin/db.py` e copia esse ficheiro para a pasta `gcadmin` da tua instalação, substituindo o anterior. Exemplo: `C:\Users\mateu\Desktop\GCAdmin\gcadmin\db.py`.
4. Executa novamente `Iniciar-Agente.bat` e introduz a mesma senha do agente.
5. Abre o cliente e testa **Contas e personagens → Abrir**.

Não é necessário executar Instalar.bat novamente. Os perfis e a configuração em `%LOCALAPPDATA%\GCAdmin` são preservados.

Foi acrescentado um teste de regressão que executa a consulta real num esquema sem CharName, com contas/personagens e inventário separados por login. O teste usa SQLite com adaptação apenas da sintaxe TOP e da chamada de parâmetros; não substitui a verificação no SQL Server real.
