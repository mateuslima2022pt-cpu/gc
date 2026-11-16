# GCAdmin · Grand Chase Season 2

Primeira versão do aplicativo de administração para Windows, com cliente desktop e agente para a máquina do servidor/VPS.

## Download

**[Baixar GCAdmin-v0.1.1.zip](https://github.com/mateuslima2022pt-cpu/gc/raw/refs/heads/main/downloads/GCAdmin-v0.1.1.zip)**

1. Baixe e extraia o ZIP para `C:\GCAdmin`.
2. Instale **Python 3.12 x64**, incluindo o Python Launcher.
3. Execute `Instalar.bat` e depois `Iniciar-GCAdmin.bat`.
4. Use **Explorar demonstração** para rever a interface sem ligar ao jogo.

O ZIP contém **código-fonte e scripts**, não um executável Windows já compilado. Para gerar os EXE no Windows, execute `Compilar-Executaveis.bat`.

## Incluído

- Perfis por IP, porta e senha; armazenamento opcional da senha via DPAPI do Windows.
- Dashboard de CPU, RAM, disco, componentes e contas.
- Pesquisa de contas, personagens e consulta de inventário.
- Criação de contas e definição de GP/cash para contas offline.
- Arranque/encerramento por Ctrl+Z e Enter, sem terminar processos à força.
- Logs, backups SQL e histórico de ações.
- Modo demonstração claramente identificado.

A integração real com SQL Server e consolas Windows exige teste na instalação do servidor. **23 testes automatizados passaram em Linux, incluindo regressão para bases sem CharName; os fluxos de navegador foram validados na 0.1.0.** GM, banimentos, edição de inventário, armazém e eventos permanecem desativados até validação das integrações.

## Documentação

- [Instalação, agente e ligação privada à VPS](GCAdmin/LEIA-PRIMEIRO.md)
- [Validação e limitações](GCAdmin/docs/VALIDACAO.md)
- [Referências e decisões](GCAdmin/docs/REFERENCIAS.md)

O agente destina-se a localhost ou VPN privada. Não inclua senhas, bases de dados ou arquivos do servidor de jogo neste repositório.

## Correção 0.1.1

Corrige o erro `Nome de coluna CharName inválido` ao abrir contas. Não é necessário alterar a base de dados. Na instalação existente, fecha o agente e substitui apenas `gcadmin/db.py` pelo ficheiro do novo ZIP; depois inicia o agente novamente.

[Instruções de atualização](GCAdmin/docs/ATUALIZACAO-0.1.1.md)
