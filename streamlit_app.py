import streamlit as st
from supabase import create_client, Client
import time
import datetime
import unicodedata

# ---------------------------------------------------------
# CONFIGURAÇÃO GERAL DA PÁGINA E ESTADOS
# ---------------------------------------------------------
st.set_page_config(page_title="Gerenciador de Almoxarifado", page_icon="📦", layout="wide")

if 'usuario_autenticado' not in st.session_state:
    st.session_state['usuario_autenticado'] = False
if 'usuario_matricula' not in st.session_state:
    st.session_state['usuario_matricula'] = ""
if 'usuario_nome' not in st.session_state:
    st.session_state['usuario_nome'] = ""
if 'is_admin' not in st.session_state:
    st.session_state['is_admin'] = False

# Dicionário para guardar quais páginas o usuário logado tem acesso
if 'acessos' not in st.session_state:
    st.session_state['acessos'] = {
        'dashboard': False, 'cadastros': False, 'movimentacoes': False, 'ajustes': False
    }

# ---------------------------------------------------------
# LIGAÇÃO À BASE DE DADOS
# ---------------------------------------------------------
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]

@st.cache_resource
def conectar_banco():
    return create_client(URL, KEY)

supabase = conectar_banco()

def formatar_unidade(valor, unidade):
    u = (unidade or "").upper()
    if u == "G" and valor >= 1000: return f"{valor / 1000:.2f} KG"
    elif u == "KG" and valor > 0 and valor < 1: return f"{valor * 1000:.0f} G"
    elif u == "ML" and valor >= 1000: return f"{valor / 1000:.2f} L"
    elif u == "L" and valor > 0 and valor < 1: return f"{valor * 1000:.0f} ML"
    return f"{valor:.2f} {u}"

# ---------------------------------------------------------
# ECRÃ DE LOGIN E CADASTRO
# ---------------------------------------------------------
def tela_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.title("🔐 Acesso Restrito (HMIM)")
        st.markdown("---")
        
        tab_login, tab_cadastro = st.tabs(["Fazer Login", "Criar Nova Conta"])
        
        with tab_login:
            with st.form("form_login"):
                email = st.text_input("E-mail Pessoal ou Corporativo")
                senha = st.text_input("Palavra-passe", type="password")
                btn_login = st.form_submit_button("Entrar", use_container_width=True)
                
                if btn_login:
                    if not email or not senha:
                        st.warning("Preencha e-mail e senha.")
                    else:
                        try:
                            resposta = supabase.auth.sign_in_with_password({"email": email.strip().lower(), "password": senha})
                            if resposta.user:
                                perfil_data = supabase.table("perfis").select("*").eq("id", resposta.user.id).execute().data
                                
                                if not perfil_data:
                                    supabase.auth.sign_out()
                                    st.error("Erro: Perfil não encontrado no banco de dados.")
                                else:
                                    perfil = perfil_data[0]
                                    if perfil['funcao'] == 'PENDENTE':
                                        supabase.auth.sign_out()
                                        st.warning("⚠️ A sua conta foi criada, mas aguarda a aprovação do Administrador de TI para acessar o sistema.")
                                    else:
                                        # Login bem sucedido - Gravamos as permissões específicas deste usuário
                                        st.session_state['usuario_autenticado'] = True
                                        st.session_state['usuario_matricula'] = perfil['matricula']
                                        st.session_state['usuario_nome'] = perfil['nome_completo']
                                        st.session_state['is_admin'] = (perfil['funcao'] == 'ADMIN')
                                        st.session_state['acessos'] = {
                                            'dashboard': perfil.get('acesso_dashboard', False),
                                            'cadastros': perfil.get('acesso_cadastros', False),
                                            'movimentacoes': perfil.get('acesso_movimentacoes', False),
                                            'ajustes': perfil.get('acesso_ajustes', False)
                                        }
                                        st.success(f"Bem-vindo(a), {perfil['nome_completo']}!")
                                        time.sleep(1)
                                        st.rerun()
                        except Exception as e:
                            st.error("Credenciais inválidas ou e-mail incorreto.")

        with tab_cadastro:
            with st.form("form_cadastro", clear_on_submit=True):
                st.caption("Preencha os dados abaixo. Após criar a conta, avise o Administrador para liberar o seu acesso.")
                nome_novo = st.text_input("Nome Completo")
                matricula_nova = st.text_input("Matrícula")
                email_novo = st.text_input("E-mail Pessoal (Será o seu login)")
                senha_nova = st.text_input("Palavra-passe (Mínimo 6 caracteres)", type="password")
                btn_cadastrar = st.form_submit_button("Solicitar Criação de Conta", use_container_width=True)
                
                if btn_cadastrar:
                    if not nome_novo or not matricula_nova or not email_novo or len(senha_nova) < 6:
                        st.warning("Preencha todos os campos. A senha deve ter no mínimo 6 caracteres.")
                    else:
                        try:
                            res_auth = supabase.auth.sign_up({"email": email_novo.strip().lower(), "password": senha_nova})
                            if res_auth.user:
                                novo_perfil = {
                                    "id": res_auth.user.id,
                                    "email": email_novo.strip().lower(),
                                    "matricula": matricula_nova.strip(),
                                    "nome_completo": nome_novo.strip(),
                                    "funcao": "PENDENTE",
                                    "acesso_dashboard": False,
                                    "acesso_cadastros": False,
                                    "acesso_movimentacoes": False,
                                    "acesso_ajustes": False
                                }
                                supabase.table("perfis").insert(novo_perfil).execute()
                                st.success("✅ Conta solicitada com sucesso! Aguarde a liberação do Administrador.")
                        except Exception as e:
                            st.error(f"Erro ao criar conta. O e-mail ou matrícula já podem estar cadastrados. Detalhe: {e}")

# ---------------------------------------------------------
# PÁGINA: GESTÃO DE USUÁRIOS (EXCLUSIVA PARA ADMIN)
# ---------------------------------------------------------
def pagina_gestao_usuarios():
    st.header("👥 Gestão de Usuários e Acessos")
    st.caption("Aprove contas, defina o cargo e arbitre manualmente quais páginas cada pessoa pode ver.")
    st.markdown("---")
    
    try:
        perfis = supabase.table("perfis").select("*").order("criado_em").execute().data
        
        if not perfis:
            st.info("Nenhum usuário cadastrado.")
            return

        for p in perfis:
            # Lógica das cores dos status
            if p['funcao'] == 'PENDENTE': status = "🔴 [PENDENTE]"
            elif p['funcao'] == 'ADMIN': status = "👑 [ADMINISTRADOR]"
            else: status = "🟢 [FUNCIONÁRIO]"
            
            # --- NOVA LÓGICA DE BLOQUEIO ---
            # Bloqueia se a matrícula do usuário do laço for igual à do usuário logado
            e_o_proprio_usuario = p['matricula'] == st.session_state['usuario_matricula']
            
            # Um bloco retrátil (expander) para cada usuário manter a tela limpa
            with st.expander(f"{status} {p['nome_completo']} - Matrícula: {p['matricula']} ({p['email']})"):
                if e_o_proprio_usuario:
                    st.info("ℹ️ Você não pode alterar as suas próprias permissões ou rebaixar seu próprio cargo.")

                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.write("**Nível Hierárquico:**")
                    nova_funcao = st.selectbox(
                        "Cargo", 
                        options=["PENDENTE", "FUNCIONARIO", "ADMIN"], 
                        index=["PENDENTE", "FUNCIONARIO", "ADMIN"].index(p['funcao']),
                        key=f"func_{p['id']}",
                        label_visibility="collapsed",
                        disabled=e_o_proprio_usuario # Bloqueia o campo
                    )
                
                with col2:
                    st.write("**Liberação de Páginas (Botões Individuais):**")
                    chk_dash = st.checkbox("📊 Dashboard (Visualizar Estoque)", value=p.get('acesso_dashboard', False), key=f"d_{p['id']}", disabled=e_o_proprio_usuario)
                    chk_mov  = st.checkbox("🔄 Movimentações (Entradas/Saídas)", value=p.get('acesso_movimentacoes', False), key=f"m_{p['id']}", disabled=e_o_proprio_usuario)
                    chk_cad  = st.checkbox("📝 Cadastros (Adicionar Catálogo/SKU)", value=p.get('acesso_cadastros', False), key=f"c_{p['id']}", disabled=e_o_proprio_usuario)
                    chk_aju  = st.checkbox("⚖️ Ajustes (Corrigir Estoque)", value=p.get('acesso_ajustes', False), key=f"a_{p['id']}", disabled=e_o_proprio_usuario)
                
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("💾 Salvar Permissões deste Usuário", key=f"btn_{p['id']}", type="primary", disabled=e_o_proprio_usuario):
                    try:
                        supabase.table("perfis").update({
                            "funcao": nova_funcao,
                            "acesso_dashboard": chk_dash,
                            "acesso_cadastros": chk_cad,
                            "acesso_movimentacoes": chk_mov,
                            "acesso_ajustes": chk_aju
                        }).eq("id", p['id']).execute()
                        
                        st.success(f"Acessos do(a) {p['nome_completo']} atualizados!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

    except Exception as e:
        st.error(f"Erro ao carregar usuários: {e}")

def pagina_dashboard():
    st.header("📊 Estoque Consolidado")
    st.markdown("---")
    try:
        pb_data = supabase.table("produtos_base").select("id, nome_oficial, unidade_medida").execute().data
        sku_data = supabase.table("produtos_skus").select("id, id_base_relacionado, descricao_real, conteudo_liquido, unidade_medida_real").execute().data
        lotes_data = supabase.table("lotes_validade").select("id, id_sku_relacionado, numero_lote, quantidade_atual, data_validade").gt("quantidade_atual", 0).execute().data
        movs_data = supabase.table("movimentacoes").select("id_lote_relacionado, tipo_movimentacao, quantidade_movimentada, data_movimentacao").eq("tipo_movimentacao", "SAÍDA").execute().data

        if pb_data and sku_data:
            mapa_skus = {s['id']: s for s in sku_data}
            mapa_lotes_historico = {}
            todos_lotes = supabase.table("lotes_validade").select("id, id_sku_relacionado").execute().data
            for l in todos_lotes:
                if l['id_sku_relacionado'] in mapa_skus: mapa_lotes_historico[l['id']] = mapa_skus[l['id_sku_relacionado']]
            
            metricas = { pb['id']: { 
                "Produto": pb['nome_oficial'], 
                "Unidade Licitacao": pb['unidade_medida'], 
                "Unidade Estoque": "", 
                "Estoque Atual Real": 0.0, 
                "Total Saidas Real": 0.0, 
                "Primeira Saida": None, 
                "Lotes": [] 
            } for pb in pb_data }

            for lote in lotes_data:
                sku = mapa_skus.get(lote['id_sku_relacionado'])
                if sku:
                    base_id = sku['id_base_relacionado']
                    qtd_real = lote['quantidade_atual'] * sku['conteudo_liquido']
                    metricas[base_id]['Estoque Atual Real'] += qtd_real
                    metricas[base_id]['Unidade Estoque'] = sku['unidade_medida_real'] or metricas[base_id]['Unidade Estoque']
                    metricas[base_id]['Lotes'].append({ "descricao": sku['descricao_real'], "lote": lote['numero_lote'], "pacotes": lote['quantidade_atual'], "qtd_real": qtd_real, "unidade": sku['unidade_medida_real'] })

            hoje = datetime.date.today()
            if movs_data:
                for mov in movs_data:
                    sku_historico = mapa_lotes_historico.get(mov['id_lote_relacionado'])
                    if sku_historico:
                        base_id = sku_historico['id_base_relacionado']
                        qtd_saida_real = mov['quantidade_movimentada'] * sku_historico['conteudo_liquido']
                        metricas[base_id]['Total Saidas Real'] += qtd_saida_real
                        data_mov = datetime.datetime.fromisoformat(mov['data_movimentacao'].replace('Z', '+00:00')).date()
                        if metricas[base_id]['Primeira Saida'] is None or data_mov < metricas[base_id]['Primeira Saida']: metricas[base_id]['Primeira Saida'] = data_mov

            # --- CÁLCULO DE MÉDIA E ESTIMATIVA ---
            for m in metricas.values():
                if m['Primeira Saida']:
                    dias_passados = max(1, (hoje - m['Primeira Saida']).days)
                    m['Media Diaria'] = m['Total Saidas Real'] / dias_passados
                    if m['Media Diaria'] > 0:
                        m['Dias Restantes'] = m['Estoque Atual Real'] / m['Media Diaria']
                    else:
                        m['Dias Restantes'] = float('inf')
                else:
                    m['Media Diaria'] = None
                    m['Dias Restantes'] = None

            # --- FUNÇÃO PARA IGNORAR ACENTOS APENAS NA ORDENAÇÃO ---
            def ignorar_acentos(texto):
                return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower()

            grupos_com_estoque = [m for m in metricas.values() if m['Estoque Atual Real'] > 0]
            
            # Ordena aplicando a função de limpeza de acentos
            grupos_com_estoque.sort(key=lambda x: ignorar_acentos(x['Produto']))

            if not grupos_com_estoque:
                st.info("Nenhum produto em estoque no momento.")
            else:
                for m in grupos_com_estoque:
                    unidade_exibicao = m['Unidade Estoque'] if m['Unidade Estoque'] else m['Unidade Licitacao']
                    
                    # Definição dos textos de exibição
                    saldo_formatado = formatar_unidade(m['Estoque Atual Real'], unidade_exibicao)
                    
                    if m['Media Diaria'] is not None:
                        media_formatada = f"{formatar_unidade(m['Media Diaria'], unidade_exibicao)} / dia"
                        est_dias = "Infinito" if m['Dias Restantes'] == float('inf') else f"{m['Dias Restantes']:.1f} dias"
                    else:
                        media_formatada = "Sem histórico de saída"
                        est_dias = "Dados não disponíveis"
                    
                    st.subheader(f"📦 {m['Produto']}")
                    
                    # Exibição das métricas alinhadas
                    c1, c2, c3 = st.columns(3)
                    c1.write(f"**Saldo Total:** {saldo_formatado}")
                    c2.write(f"**Consumo Médio:** {media_formatada}")
                    c3.write(f"**Est. Duração:** {est_dias}")
                    
                    st.markdown("**Estoque por Lote:**")
                    for l in m['Lotes']:
                        st.write(f"- {l['descricao']} (Lote: {l['lote']}): **{formatar_unidade(l['qtd_real'], l['unidade'])}** ({l['pacotes']} embalagens)")
                    
                    st.markdown("---")
    except Exception as e: st.error(f"Erro ao gerar dashboard: {e}")

def pagina_cadastros():
    st.header("📝 Cadastros de Produtos")
    st.markdown("---")
    dados_base = []
    try:
        resultado = supabase.table("produtos_base").select("id, nome_oficial, especificacao_orgao, unidade_medida").execute()
        dados_base = resultado.data
        if dados_base:
            with st.expander("Ver Catálogo Completo"): st.dataframe(dados_base, use_container_width=True)
    except Exception: pass

    st.subheader("Barcode: Cadastro de Produto Real (SKU)")
    if dados_base:
        opcoes_base = {f"{p['id']} - {p['nome_oficial']}": p['id'] for p in dados_base}
        with st.container(border=True):
            with st.form("form_sku", clear_on_submit=True):
                produto_selecionado = st.selectbox("Produto Base:", options=list(opcoes_base.keys()))
                col1, col2 = st.columns(2)
                with col1: codigo_barras = st.text_input("Cód. Barras"); conteudo_liquido = st.number_input("Conteúdo", min_value=0.01)
                with col2: descricao_real = st.text_input("Descrição"); unidade_real = st.selectbox("Unidade", ["KG", "G", "L", "ML"])
                if st.form_submit_button("Cadastrar SKU"):
                    if not codigo_barras or not descricao_real: st.warning("Preencha tudo!")
                    else:
                        supabase.table("produtos_skus").insert({"id_base_relacionado": opcoes_base[produto_selecionado], "codigo_barras": codigo_barras, "descricao_real": descricao_real, "conteudo_liquido": conteudo_liquido, "unidade_medida_real": unidade_real}).execute()
                        st.success("SKU cadastrado!"); time.sleep(1); st.rerun()

def pagina_movimentacoes():
    st.header("🔄 Movimentações de Estoque")
    col_entrada, col_saida = st.columns(2)
    with col_entrada:
        with st.container(border=True):
            st.subheader("📥 Registrar Entrada")
            skus_cadastrados = supabase.table("produtos_skus").select("*").execute().data
            if skus_cadastrados:
                opcoes_sku = {f"[{s['codigo_barras']}] {s['descricao_real']}": s['id'] for s in skus_cadastrados}
                with st.form("form_entrada", clear_on_submit=True):
                    sku_selecionado = st.selectbox("Produto:", options=list(opcoes_sku.keys()))
                    numero_lote = st.text_input("Lote")
                    data_validade = st.date_input("Validade", min_value=datetime.date.today())
                    quantidade_pacotes = st.number_input("Qtd", min_value=1)
                    if st.form_submit_button("Entrada"):
                        if not numero_lote: st.warning("Lote obrigatório")
                        else:
                            id_do_sku = opcoes_sku[sku_selecionado]
                            lote_existente = supabase.table("lotes_validade").select("*").eq("id_sku_relacionado", id_do_sku).eq("numero_lote", numero_lote).execute().data
                            if lote_existente:
                                supabase.table("lotes_validade").update({"quantidade_atual": lote_existente[0]['quantidade_atual'] + quantidade_pacotes}).eq("id", lote_existente[0]['id']).execute()
                                id_lote = lote_existente[0]['id']
                            else:
                                resultado_lote = supabase.table("lotes_validade").insert({"id_sku_relacionado": id_do_sku, "numero_lote": numero_lote, "data_validade": str(data_validade), "quantidade_atual": quantidade_pacotes}).execute()
                                id_lote = resultado_lote.data[0]['id']
                            supabase.table("movimentacoes").insert({"id_lote_relacionado": id_lote, "tipo_movimentacao": "ENTRADA", "responsavel": st.session_state['usuario_matricula'], "quantidade_movimentada": quantidade_pacotes}).execute()
                            st.success("Salvo!"); time.sleep(1); st.rerun()
    with col_saida:
        with st.container(border=True):
            st.subheader("📤 Registrar Saída")
            lotes_com_saldo = supabase.table("lotes_validade").select("*, produtos_skus(codigo_barras, descricao_real)").gt("quantidade_atual", 0).order("data_validade").execute().data
            if lotes_com_saldo:
                opcoes_saida = {f"[{l['produtos_skus']['codigo_barras']}] {l['produtos_skus']['descricao_real']} | Saldo: {l['quantidade_atual']}": l for l in lotes_com_saldo}
                with st.form("form_saida", clear_on_submit=True):
                    lote_selecionado = st.selectbox("Lote:", options=list(opcoes_saida.keys()))
                    qtd_saida = st.number_input("Qtd", min_value=1)
                    if st.form_submit_button("Saída"):
                        lote_dados = opcoes_saida[lote_selecionado]
                        if qtd_saida > lote_dados['quantidade_atual']: st.error("Saldo insuficiente!")
                        else:
                            supabase.table("lotes_validade").update({"quantidade_atual": lote_dados['quantidade_atual'] - qtd_saida}).eq("id", lote_dados['id']).execute()
                            supabase.table("movimentacoes").insert({"id_lote_relacionado": lote_dados['id'], "tipo_movimentacao": "SAÍDA", "responsavel": st.session_state['usuario_matricula'], "quantidade_movimentada": qtd_saida}).execute()
                            st.success("Salvo!"); time.sleep(1); st.rerun()

def pagina_ajustes():
    st.header("⚖️ Ajustes e Balanço")
    st.markdown("---")
    todos_lotes = supabase.table("lotes_validade").select("*, produtos_skus(codigo_barras, descricao_real)").order("data_validade").execute().data
    if todos_lotes:
        opcoes_ajuste = {f"[{l['produtos_skus']['codigo_barras']}] {l['produtos_skus']['descricao_real']} | Lote: {l['numero_lote']} | Saldo: {l['quantidade_atual']}": l for l in todos_lotes}
        with st.container(border=True):
            with st.form("form_ajuste", clear_on_submit=True):
                lote_ajuste_sel = st.selectbox("Lote:", options=list(opcoes_ajuste.keys()))
                colA, colB = st.columns(2)
                with colA: motivo_ajuste = st.selectbox("Motivo", ["AJUSTE - AVARIA", "AJUSTE - VENCIMENTO", "AJUSTE - CONTAGEM"])
                with colB: quantidade_real = st.number_input("Qtd REAL na Prateleira", min_value=0)
                if st.form_submit_button("Aplicar"):
                    lote_dados = opcoes_ajuste[lote_ajuste_sel]
                    diferenca = quantidade_real - lote_dados['quantidade_atual']
                    if diferenca != 0:
                        supabase.table("lotes_validade").update({"quantidade_atual": quantidade_real}).eq("id", lote_dados['id']).execute()
                        supabase.table("movimentacoes").insert({"id_lote_relacionado": lote_dados['id'], "tipo_movimentacao": motivo_ajuste, "responsavel": st.session_state['usuario_matricula'], "quantidade_movimentada": diferenca}).execute()
                        st.success("Ajustado!"); time.sleep(1); st.rerun()

# ---------------------------------------------------------
# LÓGICA PRINCIPAL: ROTEAMENTO DINÂMICO DE MENUS
# ---------------------------------------------------------
if not st.session_state['usuario_autenticado']:
    tela_login()
else:
    st.sidebar.title("📦 HMIM - Almoxarifado")
    st.sidebar.markdown(f"👤 Olá, **{st.session_state['usuario_nome']}**\n*(Matrícula: {st.session_state['usuario_matricula']})*")
    
    if st.sidebar.button("🚪 Sair do Sistema"):
        supabase.auth.sign_out()
        st.session_state['usuario_autenticado'] = False
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption("🔑 Nível: Administrador" if st.session_state['is_admin'] else "🔑 Nível: Funcionário")
    
    # CONSTRÓI O MENU DINAMICAMENTE BASEADO NAS PERMISSÕES
    opcoes_menu = []
    if st.session_state['acessos']['dashboard']: opcoes_menu.append("📊 Dashboard")
    if st.session_state['acessos']['cadastros']: opcoes_menu.append("📝 Cadastros")
    if st.session_state['acessos']['movimentacoes']: opcoes_menu.append("🔄 Movimentações")
    if st.session_state['acessos']['ajustes']: opcoes_menu.append("⚖️ Ajustes e Balanço")
    if st.session_state['is_admin']: opcoes_menu.append("👥 Gestão de Usuários")

    if not opcoes_menu:
        st.warning("⚠️ Você não tem permissão para aceder a nenhuma página.")
    else:
        menu_selecionado = st.sidebar.radio("Navegação:", opcoes_menu)
        if menu_selecionado == "📊 Dashboard": pagina_dashboard()
        elif menu_selecionado == "📝 Cadastros": pagina_cadastros()
        elif menu_selecionado == "🔄 Movimentações": pagina_movimentacoes()
        elif menu_selecionado == "⚖️ Ajustes e Balanço": pagina_ajustes()
        elif menu_selecionado == "👥 Gestão de Usuários": pagina_gestao_usuarios()