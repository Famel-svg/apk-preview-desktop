# APK Preview Desktop — especificação corrigida 0.2

## Produto

Aplicativo desktop Windows para abrir APKs em Android Runtime local, visualizar tela dentro da própria janela, navegar, trocar perfis de dispositivo e permitir controle/inspeção pelo Codex via MCP.

## Correção sobre spec 0.1

Spec anterior priorizava plugin do projeto Fluxo e janela externa do Android Emulator. Produto corrigido prioriza:

1. app desktop independente;
2. suporte a vários APKs, não só Fluxo;
3. preview interno clicável;
4. navegação Android pela UI própria;
5. perfis de tela selecionáveis;
6. MCP compartilhando sessão com app desktop.

## Restrição técnica

APK contém bytecode, recursos e APIs Android. Renderização genérica correta exige Android Runtime. MVP usa Android Emulator oficial como motor e captura ADB como superfície visual. Implementar runtime próprio fica fora de escopo.

## Critérios de aceite MVP

- diagnóstico mostra SDK, ADB, Emulator, AVDs e dispositivos;
- somente AVD `ApkPreview_*` e serial `emulator-*` passam;
- usuário seleciona e instala qualquer APK local;
- usuário lista e abre packages instalados;
- preview atualiza automaticamente;
- clique no preview toca posição correspondente no Android;
- voltar, início e recentes funcionam;
- perfis compacto, padrão, grande e tablet funcionam;
- árvore UI Automator aparece no painel;
- Codex recebe PNG e árvore por MCP;
- Codex instala, abre, toca e troca perfil;
- nenhum dado sai da máquina;
- plugin usa caminhos relativos.

## Próximos incrementos

- streaming por scrcpy em vez de polling PNG;
- instalação automática de SDK/AVD;
- múltiplos previews simultâneos;
- seletor semântico por texto/testTag;
- gravação de fluxo e matriz visual;
- empacotamento `.exe` via PyInstaller.
