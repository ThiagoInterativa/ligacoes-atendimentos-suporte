print("🔥 Iniciando aplicação...")

import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from io import StringIO
import pandas as pd

# =========================================================
# CONFIGURAÇÃO
# =========================================================
login_url = "https://pabx.evence.com.br/login"
export_url = "https://pabx.evence.com.br/cdr/export/csv"

email = "suporte@interativanet.com.br"
senha = "smk03657"


# =========================================================
# SESSÃO REUTILIZÁVEL
# =========================================================
@st.cache_resource
def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })
    return session


# =========================================================
# LOGIN (MANTIDO ORIGINAL)
# =========================================================
def login_pabx():
    session = get_session()

    r = session.get(login_url, timeout=120)
    soup = BeautifulSoup(r.text, "html.parser")

    csrf_input = soup.find("input", {"name": "_token"})
    csrf_token = csrf_input["value"] if csrf_input else ""

    payload = {
        "login": email,
        "senha": senha,
        "_token": csrf_token
    }

    response = session.post(login_url, data=payload, timeout=120)

    if response.url != login_url:
        return session
    else:
        raise Exception("Erro no login")


# =========================================================
# BUSCA CDR (CSV DIRETO + FILTRO CORRIGIDO)
# =========================================================
def buscar_cdr(data_inicio, data_fim):
    """
    NOVA VERSÃO:
    - usa export CSV direto
    - remove paginação
    - aplica filtros para corrigir explosão de registros
    """

    session = login_pabx()

    params = {
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

    with st.spinner("📥 Baixando relatório do PABX..."):
        r = session.get(export_url, params=params, timeout=120)

    if r.status_code != 200:
        raise Exception("Erro ao baixar CSV")

    # =========================================================
    # LEITURA DO CSV
    # =========================================================

import csv

# =========================================================
# LEITURA ROBUSTA (TAB + CSV MISTO DO PABX)
# =========================================================

raw_lines = r.text.splitlines()

# detecta automaticamente separador (TAB funciona aqui)
reader = csv.DictReader(raw_lines, delimiter="\t")

dados = []

for row in reader:
    try:
        # =====================================================
        # NORMALIZAÇÃO DAS CHAVES (REMOVE ":" E ESPAÇOS)
        # =====================================================
        clean_row = {}
        for k, v in row.items():
            if k:
                key = k.strip().replace(":", "").strip()
                clean_row[key] = v

        status = str(clean_row.get("Status", "")).strip()
        tipo = str(clean_row.get("Tipo", "")).strip()
        duracao = str(clean_row.get("Duracao", "00:00:00")).strip()

        # =====================================================
        # FILTRO MÍNIMO (NÃO ZERAR DADOS)
        # =====================================================
        if duracao == "" or ":" not in duracao:
            continue

        if status == "":
            continue

        h, m, s = duracao.split(":")
        segundos = int(h) * 3600 + int(m) * 60 + int(s)

        tecnico = str(clean_row.get("Origem", "")).strip()

        dados.append({
            "tecnico": tecnico,
            "duracao": duracao,
            "segundos": segundos,
            "status": status,
            "tipo": tipo
        })

    except:
        continue
        
# =========================================================
# KPI (CORRIGIDO PARA CONSISTÊNCIA)
# =========================================================
def calcular_kpi(dados, tecnico=None):
    total = 0
    tempo_total = 0
    alertas = []

    for d in dados:

        # 🔥 segurança extra contra ruído
        if d.get("status", "").lower() in ["", "n/a"]:
            continue

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


# =========================================================
# RANKING (CORRIGIDO)
# =========================================================
def gerar_ranking(dados):
    ranking = {}

    for d in dados:

        # 🔥 remove ruído
        if d.get("status", "").lower() in ["", "n/a"]:
            continue

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


# =========================================================
# INTERFACE STREAMLIT
# =========================================================

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


# =========================================================
# EXECUÇÃO
# =========================================================

if submit:
    try:
        if not data_inicio or not data_fim:
            st.error("Preencha as datas")

        else:
            data_inicio_str = data_inicio.strftime("%d-%m-%Y")
            data_fim_str = data_fim.strftime("%d-%m-%Y")

            dados = buscar_cdr(data_inicio_str, data_fim_str)

            if not dados:
                st.error("Nenhum dado encontrado")

            else:
                resultado = calcular_kpi(dados, tecnico)
                ranking = gerar_ranking(dados)

                col1, col2, col3 = st.columns(3)

                col1.metric("Total Chamadas", resultado["total"])
                col2.metric("Tempo Total (h)", resultado["tempo_total"])
                col3.metric("TMA (min)", resultado["tma"])

                # =================================================
                # ALERTAS > 20 MIN
                # =================================================
                if resultado["alertas"]:
                    st.markdown("### 🚨 Chamadas acima de 20 minutos")

                    texto = ""
                    for a in resultado["alertas"]:
                        texto += f"<div>Técnico: <b>{a['tecnico']}</b> - Duração: <b>{a['duracao']}</b></div>"

                    st.markdown(
                        f"""
                        <div style="background-color:#F7D7DA;padding:15px;border-radius:10px;border:1px solid #f5c2c7;color:#842029;">
                            {texto}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                # =================================================
                # RANKING
                # =================================================
                if ranking:
                    st.markdown("### 🏆 Ranking de Técnicos")
                    st.table(ranking)

    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
