print("🔥 Iniciando aplicação...")

import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ===== CONFIG =====
login_url = "https://pabx.evence.com.br/login"
cdr_url = "https://pabx.evence.com.br/cdr/pesquisar"

email = ""
senha = ""

# ===== LOGIN =====
def login_pabx():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    r = session.get(login_url)
    soup = BeautifulSoup(r.text, "html.parser")

    csrf_input = soup.find("input", {"name": "_token"})
    csrf_token = csrf_input["value"] if csrf_input else ""

    payload = {
        "login": email,
        "senha": senha,
        "_token": csrf_token
    }

    response = session.post(login_url, data=payload)

    if response.url != login_url:
        return session
    else:
        raise Exception("Erro no login")


# ===== CONSULTA =====
def buscar_cdr(data_inicio, data_fim):
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

    while True:
        payload["page"] = pagina

        r = session.get(cdr_url, params=payload, headers=headers)

        print(f"📄 Página: {pagina}")
        print("STATUS:", r.status_code)
        print("URL FINAL:", r.url)

        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table tbody tr")

        if not rows:
            print("⚠️ Nenhuma linha encontrada!")
            break

        for row in rows:
            cols = row.find_all("td")

            if len(cols) >= 6:
                tecnico = cols[4].get_text(strip=True)
                duracao = cols[5].get_text(strip=True)

                t = duracao.split(":")
                segundos = int(t[0]) * 3600 + int(t[1]) * 60 + int(t[2])

                dados.append({
                    "tecnico": tecnico,
                    "duracao": duracao,
                    "segundos": segundos
                })

        pagina += 1

    print("DADOS EXTRAÍDOS:", dados)

    return dados


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

st.title("📊 Dashboard Gestão do Helpdesk")

with st.form("form"):
    col1, col2, col3 = st.columns(3)

    with col1:
        data_inicio = st.date_input("Data início")

    with col2:
        data_fim = st.date_input("Data fim")

    with col3:
        tecnico = st.selectbox(
            "Técnico",
            ["", "102", "103", "105", "106", "109"]
        )

    submit = st.form_submit_button("🔍 Consultar")

# ===== EXECUÇÃO =====

if submit:
    try:
        if not data_inicio or not data_fim:
            st.error("Preencha as datas")
        else:
            dados = buscar_cdr(str(data_inicio), str(data_fim))

            if not dados:
                st.error("Nenhum dado encontrado")
            else:
                resultado = calcular_kpi(dados, tecnico)
                ranking = gerar_ranking(dados)

                # ===== KPI =====
                col1, col2, col3 = st.columns(3)

                col1.metric("Total Chamadas", resultado["total"])
                col2.metric("Tempo Total (h)", resultado["tempo_total"])
                col3.metric("TMA (min)", resultado["tma"])

                # ===== ALERTAS =====
                if resultado["alertas"]:
                    st.markdown("### 🚨 Chamadas acima de 20 minutos")

                    for a in resultado["alertas"]:
                        st.write(
                            f"Técnico: **{a['tecnico']}** - Duração: **{a['duracao']}**"
                        )

                # ===== RANKING =====
                if ranking:
                    st.markdown("### 🏆 Ranking de Técnicos")
                    st.table(ranking)

    except Exception as e:
        st.error(str(e))