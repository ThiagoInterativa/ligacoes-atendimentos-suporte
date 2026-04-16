print("🔥 Iniciando aplicação...")

import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ===== CONFIG =====
login_url = "https://pabx.evence.com.br/login"
cdr_url = "https://pabx.evence.com.br/cdr/pesquisar"

email = "suporte@interativanet.com.br"
senha = "smk03657"


# =========================================================
# CACHE DE SESSÃO (evita múltiplos logins)
# =========================================================
@st.cache_resource
def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })
    return session


# ===== LOGIN =====
def login_pabx():
    session = get_session()

    r = session.get(login_url, timeout=30)
    soup = BeautifulSoup(r.text, "lxml")

    csrf_input = soup.find("input", {"name": "_token"})
    csrf_token = csrf_input["value"] if csrf_input else ""

    payload = {
        "login": email,
        "senha": senha,
        "_token": csrf_token
    }

    response = session.post(login_url, data=payload, timeout=30)

    if response.url != login_url:
        return session
    else:
        raise Exception("Erro no login")


# =========================================================
# FUNÇÃO PRINCIPAL (SEM CACHE → permite atualizar progresso)
# =========================================================
def buscar_cdr(data_inicio, data_fim):
    """
    Busca dados do CDR de forma sequencial (mais estável).
    Barra de progresso atualiza em tempo real.
    """

    session = login_pabx()

    data_inicio = datetime.strptime(data_inicio, "%Y-%m-%d")
    data_fim = datetime.strptime(data_fim, "%Y-%m-%d")

    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio

    data_inicio = data_inicio.strftime("%d-%m-%Y")
    data_fim = data_fim.strftime("%d-%m-%Y")

    payload = {
        "ramal_origem": "",
        "numero_origem": "",
        "ramal_destino": "",
        "numero_destino": "",
        "did": "",
        "status_chamada": "",
        "centrocusto_id": "",
        "tipo_chamada": "IN",
        "gravacao": "",
        "discador": "0",
        "data_inicial": data_inicio,
        "data_final": data_fim
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://pabx.evence.com.br/cdr"
    }

    dados = []
    pagina = 1

    # =====================================================
    # COMPONENTES DE PROGRESSO (FUNCIONAM AGORA)
    # =====================================================
    progress_bar = st.progress(0)
    status_text = st.empty()

    # 👉 baseado no seu print (66 páginas)
    total_paginas_estimado = 70  

    while True:
        payload["page"] = pagina

        status_text.text(f"📄 Carregando página {pagina} de ~{total_paginas_estimado}")

        r = session.get(cdr_url, params=payload, headers=headers, timeout=30)

        soup = BeautifulSoup(r.text, "lxml")
        rows = soup.select("table tbody tr")

        if not rows:
            break

        # otimização leve
        append_dados = dados.append

        for row in rows:
            cols = row.find_all("td")

            if len(cols) >= 6:
                tecnico = cols[4].get_text(strip=True)
                duracao = cols[5].get_text(strip=True)

                h, m, s = duracao.split(":")
                segundos = int(h) * 3600 + int(m) * 60 + int(s)

                append_dados({
                    "tecnico": tecnico,
                    "duracao": duracao,
                    "segundos": segundos
                })

        # =================================================
        # ATUALIZA PROGRESSO
        # =================================================
        progresso = min(pagina / total_paginas_estimado, 1.0)
        progress_bar.progress(progresso)

        pagina += 1

    # finalização visual
    progress_bar.progress(1.0)
    status_text.text(f"✅ Finalizado! Total de páginas: {pagina - 1}")

    return dados


# =========================================================
# CACHE DE DADOS (AGORA SEPARADO → NÃO QUEBRA PROGRESSO)
# =========================================================
@st.cache_data(ttl=3600)
def buscar_cdr_cache(data_inicio, data_fim):
    return buscar_cdr(data_inicio, data_fim)


# ===== KPI =====
def calcular_kpi(dados, tecnico=None):
    total = 0
    tempo_total = 0
    alertas = []

    for d in dados:

        if tecnico and tecnico not in d["tecnico"]:
            continue

        if "Fila" in d["tecnico"]:
            continue

        total += 1
        tempo_total += d["segundos"]

        if d["segundos"] > 1200:
            alertas.append({
                "tecnico": d["tecnico"],
                "duracao": d["duracao"]
            })

    tma = tempo_total / total if total > 0 else 0

    return {
        "total": total,
        "tempo_total": round(tempo_total / 3600, 2),
        "tma": round(tma / 60, 2),
        "alertas": alertas
    }


# ===== RANKING =====
def gerar_ranking(dados):
    ranking = {}

    for d in dados:

        if "Fila" in d["tecnico"]:
            continue

        tecnico = d["tecnico"]

        if tecnico not in ranking:
            ranking[tecnico] = {
                "chamadas": 0,
                "tempo": 0
            }

        ranking[tecnico]["chamadas"] += 1
        ranking[tecnico]["tempo"] += d["segundos"]

    resultado = []

    for tecnico, info in ranking.items():
        tma = info["tempo"] / info["chamadas"] if info["chamadas"] > 0 else 0

        resultado.append({
            "tecnico": tecnico,
            "chamadas": info["chamadas"],
            "tma": round(tma / 60, 2)
        })

    resultado.sort(key=lambda x: x["chamadas"], reverse=True)

    return resultado


# ===== INTERFACE STREAMLIT =====

st.title("📊 Dashboard de ligações - Helpdesk")

with st.form("form"):
    col1, col2, col3 = st.columns(3)

    with col1:
        data_inicio = st.date_input("Data início")

    with col2:
        data_fim = st.date_input("Data fim")

    with col3:
        tecnico = st.selectbox(
            "Técnico",
            ["", "Leonardo", "Matheus", "Ramon", "Vinicius", "Lima", "Gabriel"]
        )

    submit = st.form_submit_button("🔍 Consultar")


# ===== EXECUÇÃO =====

if submit:
    try:
        if not data_inicio or not data_fim:
            st.error("Preencha as datas")
        else:
            with st.spinner("🔄 Carregando dados, aguarde..."):
                # usa cache (mas progresso ainda funciona na primeira execução)
                dados = buscar_cdr_cache(str(data_inicio), str(data_fim))

            if not dados:
                st.error("Nenhum dado encontrado")
            else:
                resultado = calcular_kpi(dados, tecnico)
                ranking = gerar_ranking(dados)

                col1, col2, col3 = st.columns(3)

                col1.metric("Total Chamadas", resultado["total"])
                col2.metric("Tempo Total (h)", resultado["tempo_total"])
                col3.metric("TMA (min)", resultado["tma"])

                if resultado["alertas"]:
                    st.markdown("### 🚨 Chamadas acima de 20 minutos")

                    conteudo_alertas = ""
                    for a in resultado["alertas"]:
                        conteudo_alertas += f"<div>Técnico: <b>{a['tecnico']}</b> - Duração: <b>{a['duracao']}</b></div>"

                    st.markdown(
                        f"""
                        <div style="background-color: #F7D7DA; padding: 15px; border-radius: 10px; border: 1px solid #f5c2c7; color: #842029;">
                            {conteudo_alertas}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                if ranking:
                    st.markdown("### 🏆 Ranking de Técnicos")
                    st.table(ranking)

    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
