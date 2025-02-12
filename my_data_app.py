import streamlit as st
import pandas as pd
import os
import base64
import time
import requests
from bs4 import BeautifulSoup
import urllib3
import re
import plotly.express as px

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="My Scraping App", page_icon="🚀", layout="wide")

URLS = {
    "chiens": "https://sn.coinafrique.com/categorie/chiens?page={}",
    "moutons": "https://sn.coinafrique.com/categorie/moutons?page={}",
    "poules": "https://sn.coinafrique.com/categorie/poules-lapins-et-pigeons?page={}",
    "autres": "https://sn.coinafrique.com/categorie/autres-animaux?page={}"
}

st.markdown(
    """
    <style>
    /* Cible le conteneur du groupe de boutons radio */
    div[role="radiogroup"] {
        display: flex;
        flex-direction: row;
        justify-content: space-around; /* Vous pouvez ajuster l'espacement si nécessaire */
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.header("Navigation")

option = st.radio(
    "Sélectionnez une section :",
    ("Scraping", "Dashboard", "WebScraper Data", "Évaluer l'App")
)

st.write("Vous avez sélectionné :", option)


def clean_data(df):
    df = df.copy()

    if "prix" in df.columns:
        df["prix"] = df["prix"].astype(str)
        df["prix"] = df["prix"].replace("Prix sur demande", None)
        df["prix"] = df["prix"].apply(lambda x: re.sub(r"[^\d]", "", x) if isinstance(x, str) else x)
        df["prix"] = pd.to_numeric(df["prix"], errors="coerce")
        if df["prix"].notna().sum() > 0:
            mean_price = df["prix"].mean(skipna=True)
            df["prix"].fillna(mean_price, inplace=True)
        df["prix"] = df["prix"].astype(int)

    if "adresse" in df.columns:
        df["adresse"] = df["adresse"].astype(str).str.strip()
        df["adresse"] = df["adresse"].replace(["N/A", "Inconnu", "Non Spécifié"], "Non Renseigné")
        df["adresse"] = df["adresse"].str.replace("location_on", "", regex=False).str.strip()

    df.drop_duplicates(inplace=True)

    print(df.info())
    print(df.head())

    return df


import numpy as np
from scipy.stats import gaussian_kde


def display_dashboard(df, category):
    st.subheader(f"📊 Analyse alternative des données pour {category}")

    df = clean_data(df)
    df.columns = df.columns.str.lower()

    if "prix" not in df.columns or df.empty:
        st.warning("⚠️ Aucune donnée valide pour afficher le dashboard.")
        return

    df_filtered = df[df["prix"] < 10_000_000]

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Nombre d'annonces", len(df))


    st.markdown("### 📊 Distribution des Prix (KDE Plot)")
    prices = df_filtered["prix"].values
    kde = gaussian_kde(prices)
    xmin, xmax = prices.min(), prices.max()
    x_range = np.linspace(xmin, xmax, 200)
    y_density = kde(x_range)
    fig1 = px.line(x=x_range, y=y_density,
                   title="KDE Plot des Prix",
                   labels={"x": "Prix (FCFA)", "y": "Densité"})
    st.plotly_chart(fig1, use_container_width=True)

    st.markdown("### 🏙️ Nombre d'annonces par Localisation")
    if "adresse" in df.columns:
        loc_counts = df["adresse"].value_counts().reset_index()
        loc_counts.columns = ["adresse", "nombre_annonces"]
        fig2 = px.bar(
            loc_counts,
            x="adresse",
            y="nombre_annonces",
            title="Nombre d'annonces par Localisation",
            labels={"adresse": "Localisation", "nombre_annonces": "Nombre d'annonces"},
            color="nombre_annonces",
            color_continuous_scale="Blues"
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("La colonne 'adresse' n'est pas disponible pour cette analyse.")

    st.markdown("### 🍩 Répartition par Localisation (Donut Chart)")
    if "adresse" in df.columns:
        loc_distribution = df["adresse"].value_counts().reset_index()
        loc_distribution.columns = ["adresse", "nombre"]
        fig3 = px.pie(
            loc_distribution,
            values="nombre",
            names="adresse",
            title="Répartition des annonces par Localisation",
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("La colonne 'adresse' n'est pas disponible pour cette analyse.")


def scrap_data(base_url, category, max_pages=1):
    all_data = []
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/132.0.0.0 Safari/537.36")
    }

    for page_num in range(1, max_pages + 1):
        url = base_url.format(page_num)
        print(f"🔍 Scraping de la page {page_num} : {url}")

        response = requests.get(url, headers=headers, verify=False)
        if response.status_code != 200:
            print(f"⚠️ Erreur sur la page {page_num} : HTTP {response.status_code}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        containers = soup.select("div.col.s6.m4.l3")
        print(f"🔎 Trouvé {len(containers)} annonces sur la page {page_num}")

        for container in containers:
            try:
                details_elem = container.select_one(".ad__card-description")
                details = details_elem.get_text(strip=True) if details_elem else "N/A"

                price_elem = container.select_one(".ad__card-price")
                location_elem = container.select_one(".ad__card-location")

                price_text = (price_elem.get_text(strip=True)
                              .replace("FCFA", "")
                              .replace(",", "")
                              .strip() if price_elem else "N/A")
                location_text = location_elem.get_text(strip=True) if location_elem else "N/A"

                image_element = container.select_one("img")
                image_url = image_element["src"].strip() if image_element and image_element.has_attr("src") else "N/A"

                all_data.append({
                    "Détails": details,
                    "Prix": price_text,
                    "Localisation": location_text,
                    "Image URL": image_url
                })
            except Exception as e:
                print(f"⚠️ Erreur lors de l'extraction d'une annonce : {e}")

        time.sleep(3)

    file_path = f"data/selenium_data/{category.lower().replace(' ', '_')}.csv"

    if os.path.exists(file_path):
        try:
            old_df = pd.read_csv(file_path)
            if old_df.empty:
                print(f"⚠️ Le fichier {file_path} est vide, il sera ignoré.")
                old_df = pd.DataFrame()
            else:
                print(f"📂 Chargement des anciennes données depuis : {file_path}")
        except pd.errors.EmptyDataError:
            print(f"⚠️ Erreur : Le fichier {file_path} est vide ou corrompu. Il sera ignoré.")
            old_df = pd.DataFrame()
    else:
        old_df = pd.DataFrame()

    if all_data:
        new_df = pd.DataFrame(all_data)
        combined_df = pd.concat([old_df, new_df], ignore_index=True).drop_duplicates()
        combined_df.to_csv(file_path, index=False)
        print(f"✅ Données sauvegardées pour {category} dans : {file_path}")
    else:
        print(f"⚠️ Aucun nouveau résultat. Conservation des anciennes données.")

def load_existing_data(selected_category, clean_data_option):
    if selected_category == "Toutes les catégories":
        for category in URLS.keys():
            file_path = f"data/selenium_data/{category.lower().replace(' ', '_')}.csv"
            try:
                df = pd.read_csv(file_path)
                if clean_data_option:
                    df = clean_data(df)
                st.markdown(f"### 📊 Données existantes pour **{category}**")
                st.dataframe(df)
            except FileNotFoundError:
                st.warning(f"⚠️ Aucune donnée existante pour {category}.")
    else:
        file_path = f"data/selenium_data/{selected_category.lower().replace(' ', '_')}.csv"
        try:
            df = pd.read_csv(file_path)
            if clean_data_option:
                df = clean_data(df)
            st.markdown(f"### 📊 Données existantes pour **{selected_category}**")
            st.dataframe(df)
        except FileNotFoundError:
            st.warning(f"⚠️ Aucune donnée existante pour {selected_category}.")

if option == "Scraping":
    st.header("Scraping de données")
    st.write("Scrapez des données à partir de plusieurs pages.")

    selected_category = st.selectbox("Choisir une catégorie :", ["Toutes les catégories"] + list(URLS.keys()))
    num_pages = st.number_input("Nombre de pages à scraper :", min_value=1, max_value=50, value=2)
    clean_data_option = st.checkbox("Nettoyer les données avant affichage", value=True)

    st.markdown("### Données existantes")
    load_existing_data(selected_category, clean_data_option)

    if st.button("Lancer le scraping"):
        with st.spinner("Scraping en cours.."):
            if selected_category == "Toutes les catégories":
                for category, url in URLS.items():
                    scrap_data(url, category, max_pages=num_pages)
            else:
                scrap_data(URLS[selected_category], selected_category, max_pages=num_pages)

elif option == "Dashboard":
    st.header("📈 Dashboard des données scrapées")
    selected_dashboard_category = st.selectbox("Choisir une catégorie à analyser :", list(URLS.keys()))
    file_path = f"data/webscraper_data/{selected_dashboard_category.lower().replace(' ', '_')}.csv"
    try:
        df_dashboard = pd.read_csv(file_path)
        display_dashboard(df_dashboard, selected_dashboard_category)
    except FileNotFoundError:
        st.warning(f"⚠️ Aucune donnée trouvée pour {selected_dashboard_category}. Veuillez scraper d'abord.")

elif option == "WebScraper Data":
    st.header("🌐 Données WebScraper")
    data_folder = "data/webscraper_data"
    if not os.path.exists(data_folder):
        st.warning("⚠️ Aucune donnée trouvée. Scrapez d'abord !")
    else:
        for file in os.listdir(data_folder):
            file_path = os.path.join(data_folder, file)
            with open(file_path, "rb") as f:
                st.download_button(f"⬇️ Télécharger {file}", data=f, file_name=file)

elif option == "Évaluer l'App":
    st.header("Évaluer l'application")
    st.write("Merci de remplir ce formulaire pour nous aider à améliorer l'application.")
    kobo_form_url = "https://ee.kobotoolbox.org/x/bCaC927U"
    iframe_code = f'<iframe src="{kobo_form_url}" width="100%" height="600px"></iframe>'
    st.markdown(iframe_code, unsafe_allow_html=True)
