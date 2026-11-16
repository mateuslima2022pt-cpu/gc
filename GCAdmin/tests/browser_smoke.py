"""Optional browser smoke test. Requires playwright and a local Chromium executable.

Run the client with --no-open --port 18741 before this script.
"""
import os
from pathlib import Path
import time
from playwright.sync_api import sync_playwright

output = Path(os.environ.get('GCADMIN_PREVIEWS', 'work/previews'))
output.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'),
                                headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('http://127.0.0.1:18741/')
    page.get_by_text('Conectar ao servidor', exact=True).wait_for()
    page.screenshot(path=str(output / '01-conexao.png'), full_page=True)
    page.locator('[data-action="demo"]').click()
    page.get_by_role('heading', name='Visão geral', exact=True).wait_for()
    page.screenshot(path=str(output / '02-dashboard.png'), full_page=True)
    page.locator('[data-action="nav"][data-page="accounts"]').click()
    page.get_by_role('button', name='Abrir').first.wait_for()
    page.locator('[data-action="select-account"][data-id="84267"]').first.click()
    page.get_by_role('heading', name='Elesis', exact=True).wait_for()
    page.screenshot(path=str(output / '03-contas.png'), full_page=True)
    writes = []
    page.on('request', lambda r: writes.append(r.url) if r.method == 'POST' else None)
    page.locator('[data-action="balance"]').click()
    page.locator('#balance-form input[name="confirm"]').check()
    before = len(writes)
    page.get_by_role('button', name='Cancelar', exact=True).click()
    page.wait_for_timeout(150)
    assert len(writes) == before, 'Cancelar não pode submeter alterações de saldo.'
    page.locator('[data-action="balance"]').click()
    page.locator('#balance-gp').fill('2500000')
    page.locator('#balance-cash').fill('123456')
    page.locator('#balance-form input[name="confirm"]').check()
    page.get_by_role('button', name='Aplicar saldos').click()
    page.get_by_text('Saldos definidos e operação registada.', exact=True).wait_for()
    assert '123' in page.locator('tr[data-id="84267"]').inner_text()
    page.locator('[data-action="select-account"][data-id="84269"]').first.click()
    page.locator('[data-action="balance"]').click()
    page.locator('#balance-form input[name="confirm"]').check()
    page.get_by_role('button', name='Aplicar saldos').click()
    page.get_by_text('Sai da conta antes de alterar os saldos.', exact=True).wait_for()
    page.locator('[data-action="close-modal"]').first.click()
    page.locator('[data-action="create"]').click()
    login = 'ui' + str(time.time_ns())[-12:]
    page.locator('#new-login').fill(login)
    page.locator('#new-password').fill('teste12345')
    page.locator('#new-email').fill('ui@example.com')
    page.get_by_role('button', name='Criar conta', exact=True).last.click()
    page.get_by_text('Conta criada: três personagens iniciais.', exact=True).wait_for()
    assert page.locator('.character-card').count() == 3
    page.locator('[data-action="detail-tab"][data-tab="inventory"]').click()
    page.get_by_text('Mochila (+10)', exact=True).wait_for()
    page.locator('[data-action="nav"][data-page="server"]').click()
    page.get_by_role('heading', name='Controlo dos componentes', exact=True).wait_for()
    page.screenshot(path=str(output / '04-servidor.png'), full_page=True)
    page.locator('[data-action="backup"]').click()
    page.locator('#backup-form input[type="checkbox"]').check()
    page.get_by_role('button', name='Iniciar backup', exact=True).click()
    page.get_by_text('Operação concluída', exact=True).wait_for()
    page.get_by_role('button', name='Fechar janela', exact=True).click()
    page.locator('[data-action="nav"][data-page="audit"]').click()
    page.get_by_text('Definir GP/cash', exact=True).first.wait_for()
    page.screenshot(path=str(output / '05-historico.png'), full_page=True)
    page.locator('[data-action="nav"][data-page="logs"]').click()
    page.get_by_text('DEMONSTRACAO.log', exact=True).wait_for()
    page.locator('[data-action="disconnect"]').first.click()
    page.get_by_text('Conectar ao servidor', exact=True).wait_for()
    page.locator('#profile-name').fill('Local de teste')
    before = len([url for url in writes if url.endswith('/api/connect')])
    page.locator('[data-action="save-profile"]').click()
    page.get_by_text('Perfil guardado.', exact=True).wait_for()
    page.wait_for_timeout(150)
    assert len([url for url in writes if url.endswith('/api/connect')]) == before
    page.set_viewport_size({'width': 1100, 'height': 800})
    page.locator('[data-action="demo"]').click()
    page.get_by_role('heading', name='Visão geral', exact=True).wait_for()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    print('PASS: conexão, dashboard, contas, saldos, bloqueio online, criação, inventário, gestão, backup demo, auditoria, logs e perfis.')
    print('Erros JavaScript:', errors)
    assert not errors
    browser.close()
