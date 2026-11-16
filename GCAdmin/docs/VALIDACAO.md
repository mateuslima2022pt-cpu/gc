# Validação da entrega 0.1.1

## Executado neste ambiente

- Ambiente: Linux, Python 3.12, Node.js e Chromium headless.
- **23 testes automatizados passaram**, executados com `python -m unittest discover -s tests -v`.
- Sintaxe Python de todos os módulos e JSON do exemplo validados.
- JavaScript validado com `node --check web/app.js`.
- Teste de navegador com Playwright/Chromium passou, sem erros de JavaScript.

## Cobertura funcional

- Dashboard e demonstração explicitamente identificada.
- Seleção de conta e três personagens iniciais em demonstração.
- Definição de saldo e histórico com valores anterior/posterior.
- Bloqueio de alteração de saldo numa conta online.
- Botão Cancelar não envia alterações; Salvar perfil não conecta automaticamente.
- Criação de conta de demonstração e rejeição de login duplicado.
- Consulta de inventário, gestão, backup simulado, logs e auditoria.
- Perfis e layout sem overflow horizontal a 1100px.
- Agente HTTP exige token inclusive para consulta de estado.
- Limitação de tentativas de autenticação.
- Gateway local encaminha pedidos autenticados para o agente e preserva os erros de autenticação.
- Gateway local exige nonce e verifica Host e Origin.
- Senha não é persistida quando não se escolhe guardá-la.
- Rejeição de HTTP para hosts públicos; aceitação de loopback, rede privada e CGNAT VPN.
- Pedidos de controlo precisam de confirmação e recusam componentes não previstos.
- Encerramento do GameServer bloqueado com contas marcadas online.
- Sequência simulada de encerramento sem contas online.
- Transação SQL faz rollback/fecha a ligação quando ocorre falha.
- Limites e tipos numéricos dos saldos.
- Senha de criação de conta não aparece no histórico.

## Ainda não validado

- Compilação e execução dos .exe Windows e instalação das dependências nessa máquina.
- Janela nativa Edge WebView2/pywebview e proteção DPAPI no Windows.
- Execução das consultas contra o SQL Server real da Season 2.
- Envio Win32 de Ctrl+Z/Enter e controlo dos processos reais.
- Encerramento/reinício da VPS com validação posterior de persistência.
- Backup e restauro reais das quatro bases.
- Estado das consolas após desconectar a sessão RDP.
- Desempenho e segurança operacional sob carga/múltiplos utilizadores.

Os testes locais não afirmam compatibilidade de produção com uma VPS ainda não configurada. A API foi construída com base nos nomes de campos e procedimentos já observados nesta instalação; a primeira integração Windows deve ser feita com contas de teste e cópias das bases.

## Primeiro teste recomendado no Windows

1. Abrir o cliente em demonstração e rever as telas.
2. Iniciar o agente em localhost e conectar com a senha exclusiva.
3. Conferir os sete componentes e as contagens da base, sem alterações.
4. Criar uma conta de teste e confirmar 0/1/2, nível 1, XP 2020.
5. Definir GP/cash com conta offline e conferir no SQL/jogo.
6. Encerrar com todos os jogadores fora; verificar sequência e progresso após reiniciar.
7. Criar backup SQL numa pasta com permissões adequadas e realizar um restauro de teste separado.

As funções pendentes têm botões desativados e nenhum endpoint de escrita. Não se deve habilitá-las só removendo o atributo `disabled` da interface.

Atualização 0.1.1: teste de regressão para abertura de conta sem Characters.CharName, executando a consulta real num esquema de teste sem essa coluna. Validação em SQL Server real continua pendente.
