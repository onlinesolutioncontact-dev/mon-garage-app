import streamlit as st
import pandas as pd
import os
import json
from datetime import datetime
from PIL import Image, ImageOps
from fpdf import FPDF
import urllib.parse
from pypdf import PdfWriter, PdfReader # NOUVEAU : Pour fusionner les dossiers

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Garage Manager V16", page_icon="🏎️", layout="wide")

os.makedirs("photos", exist_ok=True)
os.makedirs("factures", exist_ok=True)

FILES = {
    "maintenance": "base_entretien_propre.csv",
    "carburant": "suivi_carburant.csv",
    "config": "garage_config.json"
}

# --- 2. DONNÉES PERSO ---
DATA_INIT = {
    "BMW": {"Marque": "BMW", "Modele": "Série 3 (L6)", "Plaque": "GS-194-AH", "Moteur": "2.8L Essence (6 Cyl)", "Huile": "6.5L (5W30)", "Conso_Th": "9.0L/100"},
    "Citroen c5": {"Marque": "Citroën", "Modele": "C5 II", "Plaque": "CG-627-VC", "Moteur": "2.0 HDi 160", "Huile": "5.0L (5W30)", "Conso_Th": "5.8L/100"},
    "Peugeot 307": {"Marque": "Peugeot", "Modele": "307", "Plaque": "AS-091-NE", "Moteur": "1.6 HDi 110", "Huile": "3.75L (5W30)", "Conso_Th": "5.0L/100"},
    "Twingo": {"Marque": "Renault", "Modele": "Twingo II", "Plaque": "AT-164-ZJ", "Moteur": "1.2 16V 75ch", "Huile": "4.0L (10W40)", "Conso_Th": "5.1L/100"},
    "LAtitude": {"Marque": "Renault", "Modele": "Latitude", "Plaque": "BV-158-LT", "Moteur": "2.0 dCi 175", "Huile": "7.4L (5W30)", "Conso_Th": "6.5L/100"},
    "kangoo": {"Marque": "Renault", "Modele": "Kangoo", "Plaque": "XX-XXX-XX", "Moteur": "1.9d (Atmo)", "Huile": "4.5L (10W40)", "Conso_Th": "6.5L/100"}
}

# --- 3. FONCTIONS ---

def load_config():
    data = {}
    if os.path.exists(FILES["config"]):
        with open(FILES["config"], "r") as f:
            try: data = json.load(f)
            except: data = {}
    updated = False
    for car_key, car_info in DATA_INIT.items():
        found = False
        for k in data.keys():
            if k == car_key or k == f"Voiture - {car_key}":
                found = True
                if "Moteur" in data[k] and data[k]["Moteur"] != car_info["Moteur"]:
                    data[k].update(car_info); updated = True
                break
        if not found: data[car_key] = car_info; updated = True
    if updated: save_config(data)
    return data

def save_config(data):
    with open(FILES["config"], "w") as f: json.dump(data, f, indent=4)

def load_data(key):
    path = FILES[key]
    cols = ['Date', 'Vehicule', 'Kilometrage', 'Description', 'Cout', 'Facture'] if key == "maintenance" else ['Date', 'Vehicule', 'Kilometrage', 'Litres', 'Prix_Total', 'Conso_Calc']
    try:
        df = pd.read_csv(path)
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        for c in cols:
            if c not in df.columns: df[c] = None
        if key == "maintenance": df['Facture'] = df['Facture'].astype(str).replace('nan', None)
        return df
    except FileNotFoundError: return pd.DataFrame(columns=cols)

def save_data(df, key): df.to_csv(FILES[key], index=False)

def save_uploaded_file(uploaded_file):
    if uploaded_file is not None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{uploaded_file.name}"
        path = os.path.join("factures", filename)
        with open(path, "wb") as f: f.write(uploaded_file.getbuffer())
        return path
    return None

def load_and_crop_image(image_path, target_size=(400, 300)):
    try:
        img = Image.open(image_path)
        img = ImageOps.fit(img, target_size, Image.Resampling.LANCZOS)
        return img
    except Exception: return None

def get_car_image_path(car_name):
    clean = car_name.replace("Voiture - ", "").strip()
    candidates = [car_name, clean]
    for c in candidates:
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            path = os.path.join("photos", c + ext)
            if os.path.exists(path): return path
    return None

def generer_pdf_complet(car_name, df_car):
    """Génère un PDF Récapitulatif + Fusionne les factures à la suite"""
    
    # 1. Création du PDF Récapitulatif (Tableau) avec FPDF
    pdf_recap = FPDF()
    pdf_recap.add_page()
    pdf_recap.set_font("Arial", 'B', 16)
    pdf_recap.cell(0, 10, f"Dossier Entretien - {car_name}", ln=True, align='C')
    pdf_recap.ln(10)
    pdf_recap.set_font("Arial", '', 12)
    pdf_recap.cell(0, 10, f"Dossier genere le {datetime.now().strftime('%d/%m/%Y')}", ln=True)
    pdf_recap.ln(5)
    
    # Tableau
    pdf_recap.set_font("Arial", 'B', 10)
    pdf_recap.cell(25, 10, "Date", 1)
    pdf_recap.cell(25, 10, "Km", 1)
    pdf_recap.cell(95, 10, "Description", 1)
    pdf_recap.cell(25, 10, "Prix", 1)
    pdf_recap.cell(20, 10, "PJ", 1)
    pdf_recap.ln()
    
    pdf_recap.set_font("Arial", '', 9)
    total = 0
    factures_a_fusionner = []

    for _, row in df_car.iterrows():
        d = row['Date'].strftime('%d/%m/%Y') if pd.notna(row['Date']) else "-"
        c = row['Cout'] if pd.notna(row['Cout']) else 0
        total += c
        
        has_facture = "NON"
        f_path = str(row['Facture'])
        if f_path and f_path != "None" and f_path != "" and os.path.exists(f_path):
            has_facture = "OUI"
            # On mémorise la facture pour la fusionner plus tard
            factures_a_fusionner.append((row['Description'], f_path))

        pdf_recap.cell(25, 10, d, 1)
        pdf_recap.cell(25, 10, str(row['Kilometrage']), 1)
        pdf_recap.cell(95, 10, str(row['Description'])[:60], 1)
        pdf_recap.cell(25, 10, f"{c:.0f} E", 1)
        pdf_recap.cell(20, 10, has_facture, 1)
        pdf_recap.ln()
    
    pdf_recap.ln(5)
    pdf_recap.set_font("Arial", 'B', 12)
    pdf_recap.cell(0, 10, f"TOTAL INVESTI : {total:,.2f} Euros", ln=True, align='R')
    
    # On sauvegarde le récapitulatif temporairement
    temp_recap = "temp_recap.pdf"
    pdf_recap.output(temp_recap)
    
    # 2. Fusion avec PyPDF
    merger = PdfWriter()
    
    # Ajout du récapitulatif en premier
    merger.append(temp_recap)
    
    # Ajout des factures
    for desc, f_path in factures_a_fusionner:
        try:
            ext = f_path.split('.')[-1].lower()
            
            # Si c'est un PDF, on l'ajoute directement
            if ext == 'pdf':
                merger.append(f_path)
            
            # Si c'est une image, on la convertit en page PDF d'abord
            elif ext in ['jpg', 'jpeg', 'png', 'webp']:
                pdf_img = FPDF()
                pdf_img.add_page()
                pdf_img.set_font("Arial", 'B', 12)
                pdf_img.cell(0, 10, f"PJ : {desc}", ln=True)
                # On essaie d'ajuster l'image à la page (A4 = 210mm large)
                pdf_img.image(f_path, x=10, y=30, w=190)
                
                temp_img_pdf = "temp_img.pdf"
                pdf_img.output(temp_img_pdf)
                merger.append(temp_img_pdf)
                # Pas de suppression immédiate pour éviter les conflits d'accès
        except Exception as e:
            print(f"Erreur fusion {f_path}: {e}")

    # 3. Sauvegarde finale
    final_filename = f"Dossier_Complet_{car_name.replace(' ', '_')}.pdf"
    merger.write(final_filename)
    merger.close()
    
    # Nettoyage temporaire
    if os.path.exists(temp_recap): os.remove(temp_recap)
    if os.path.exists("temp_img.pdf"): os.remove("temp_img.pdf")
    
    return final_filename

# --- 4. CHARGEMENT ---
garage_config = load_config()
df_maint = load_data("maintenance")
df_fuel = load_data("carburant")

cars_in_csv = df_maint['Vehicule'].dropna().unique()
for c in cars_in_csv:
    if c not in garage_config:
        garage_config[c] = {"Marque": "Inconnu", "Modele": "-", "Plaque": "-", "Moteur": "-", "Huile": "-", "Conso_Th": "-"}
save_config(garage_config)
all_cars = sorted(list(garage_config.keys()))

# --- 5. CSS ---
st.markdown("""
    <style>
    .stApp {background-color: #f8f9fa;}
    div[data-testid="stMetric"] { background-color: white; padding: 10px; border-radius: 8px; border: 1px solid #ddd; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .email-btn { display: block; width: 100%; padding: 12px; background-color: #d9534f; color: white; text-align: center; border-radius: 5px; text-decoration: none; font-weight: bold; margin-top: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- 6. NAVIGATION ---
if 'selected_car' not in st.session_state: st.session_state.selected_car = "Vue d'ensemble"
st.sidebar.title("🏁 Garage V16")
nav = st.sidebar.selectbox("Navigation", ["Vue d'ensemble"] + all_cars, index=0 if st.session_state.selected_car not in all_cars else all_cars.index(st.session_state.selected_car)+1)
if nav != st.session_state.selected_car: st.session_state.selected_car = nav; st.rerun()
st.sidebar.markdown("---")

# --- 7. SIDEBAR ---
with st.sidebar.expander("⚙️ Gérer le Parc Auto"):
    tab_add, tab_del = st.tabs(["Ajouter", "Supprimer"])
    with tab_add:
        with st.form("new_c"):
            st.write(" **Nouveau Véhicule**")
            n_nom = st.text_input("Nom (ex: Clio Rouge)")
            c1, c2 = st.columns(2)
            n_marq = c1.text_input("Marque")
            n_mod = c2.text_input("Modèle")
            n_plaq = c1.text_input("Plaque")
            n_mot = c2.text_input("Moteur")
            n_huil = st.text_input("Huile")
            uploaded_photo = st.file_uploader("Photo du véhicule", type=['jpg', 'png', 'jpeg'])
            if st.form_submit_button("Créer"):
                if n_nom and n_nom not in garage_config:
                    garage_config[n_nom] = {"Marque": n_marq, "Modele": n_mod, "Plaque": n_plaq, "Moteur": n_mot, "Huile": n_huil, "Conso_Th": "-"}
                    save_config(garage_config)
                    if uploaded_photo:
                        ext = uploaded_photo.name.split('.')[-1]
                        with open(os.path.join("photos", f"{n_nom}.{ext}"), "wb") as f: f.write(uploaded_photo.getbuffer())
                    st.success(f"{n_nom} ajouté !"); st.rerun()
                else: st.error("Nom invalide")
    with tab_del:
        to_del = st.selectbox("Supprimer", [""] + all_cars)
        if st.button("🗑️ Confirmer"):
            if to_del in garage_config:
                del garage_config[to_del]; save_config(garage_config)
                df_maint = df_maint[df_maint['Vehicule'] != to_del]; save_data(df_maint, "maintenance")
                df_fuel = df_fuel[df_fuel['Vehicule'] != to_del]; save_data(df_fuel, "carburant")
                st.session_state.selected_car = "Vue d'ensemble"; st.success("Supprimé !"); st.rerun()

if all_cars:
    with st.sidebar.expander("🛠️ Saisie Rapide (+Facture)"):
        with st.form("quick"):
            idx_def = all_cars.index(st.session_state.selected_car) if st.session_state.selected_car in all_cars else 0
            q_car = st.selectbox("Véhicule", all_cars, index=idx_def)
            q_type = st.radio("Type", ["Entretien", "Plein"], horizontal=True)
            q_date = st.date_input("Date", datetime.now())
            q_km = st.number_input("Km", step=100)
            q_prix = st.number_input("Prix (€)", min_value=0.0)
            q_desc = st.text_input("Description (si Entretien)")
            q_litres = st.number_input("Litres (si Plein)", step=0.1)
            q_file = st.file_uploader("Facture", type=['png', 'jpg', 'jpeg', 'pdf'])
            if st.form_submit_button("Enregistrer"):
                if q_type == "Entretien":
                    f_path = save_uploaded_file(q_file)
                    new = pd.DataFrame([{'Date': pd.to_datetime(q_date), 'Vehicule': q_car, 'Kilometrage': q_km, 'Description': q_desc, 'Cout': q_prix, 'Facture': f_path}])
                    df_maint = pd.concat([df_maint, new], ignore_index=True); save_data(df_maint, "maintenance")
                else:
                    conso = 0
                    prev = df_fuel[df_fuel['Vehicule'] == q_car].sort_values('Kilometrage')
                    if not prev.empty:
                        dist = q_km - prev.iloc[-1]['Kilometrage']
                        if dist > 0: conso = (q_litres / dist) * 100
                    new = pd.DataFrame([{'Date': pd.to_datetime(q_date), 'Vehicule': q_car, 'Kilometrage': q_km, 'Litres': q_litres, 'Prix_Total': q_prix, 'Conso_Calc': round(conso, 2)}])
                    df_fuel = pd.concat([df_fuel, new], ignore_index=True); save_data(df_fuel, "carburant")
                st.success("Enregistré !"); st.rerun()

# --- 8. PAGE PRINCIPALE ---
if st.session_state.selected_car == "Vue d'ensemble":
    st.title("🏎️ Garage - Vue d'Ensemble")
    if not all_cars: st.info("Aucun véhicule.")
    cols = st.columns(3)
    for i, car in enumerate(all_cars):
        with cols[i % 3]:
            with st.container(border=True):
                img_path = get_car_image_path(car)
                if img_path:
                    pil_img = load_and_crop_image(img_path, target_size=(400, 300))
                    if pil_img: st.image(pil_img, use_container_width=True)
                else: st.markdown("<div style='height:150px; background:#eee; display:flex; align-items:center; justify-content:center; color:#888;'>Pas de photo</div>", unsafe_allow_html=True)
                if st.button(f"📂 {car.replace('Voiture - ', '')}", key=f"btn_{car}", use_container_width=True): st.session_state.selected_car = car; st.rerun()
                infos = garage_config.get(car, {})
                st.markdown(f"<div style='margin-top:5px; line-height:1.4;'><b>{infos.get('Marque', '-')} {infos.get('Modele', '')}</b><br>🆔 {infos.get('Plaque', '-')}<br>⛽ {infos.get('Moteur', '-')}</div>", unsafe_allow_html=True)
else:
    car = st.session_state.selected_car
    st.button("⬅️ Retour", on_click=lambda: st.session_state.update(selected_car="Vue d'ensemble"))
    infos = garage_config.get(car, {})
    c1, c2 = st.columns([1, 2])
    with c1:
        img_path = get_car_image_path(car)
        if img_path:
            pil_img = load_and_crop_image(img_path, target_size=(500, 350))
            if pil_img: st.image(pil_img)
        else: st.info("Image manquante")
    with c2:
        st.title(car)
        st.markdown(f"""
        ### 📋 Fiche Technique
        - **Marque / Modèle** : {infos.get('Marque', '-')} {infos.get('Modele', '-')}
        - **Plaque** : `{infos.get('Plaque', '-')}`
        - **Moteur** : **{infos.get('Moteur', '-')}**
        - **Huile** : 🛢️ {infos.get('Huile', 'Non renseigné')}
        """)
        df_c = df_maint[df_maint['Vehicule'] == car]
        df_f = df_fuel[df_fuel['Vehicule'] == car]
        k1, k2, k3 = st.columns(3)
        k1.metric("Km Compteur", f"{df_c['Kilometrage'].max() if not df_c.empty else 0:,.0f} km")
        k2.metric("Total Entretien", f"{df_c['Cout'].sum():,.0f} €")
        k3.metric("Conso Réelle", f"{df_f[df_f['Conso_Calc']>0]['Conso_Calc'].mean() if not df_f.empty else 0:.1f} L/100")

    tab_m, tab_f, tab_a = st.tabs(["🔧 Entretien", "⛽ Carburant", "🚨 Alertes"])
    with tab_m:
        with st.expander("➕ AJOUTER UNE LIGNE & FACTURE (Clique ici)", expanded=False):
            with st.form("add_line_main"):
                c1, c2, c3 = st.columns(3)
                a_date = c1.date_input("Date", datetime.now())
                a_km = c2.number_input("Kilométrage", step=100)
                a_prix = c3.number_input("Prix (€)", min_value=0.0)
                a_desc = st.text_input("Description de l'intervention")
                a_file = st.file_uploader("Joindre une facture (PDF/Image)", type=['pdf', 'jpg', 'png'])
                if st.form_submit_button("✅ VALIDER L'AJOUT", type="primary"):
                    f_path = save_uploaded_file(a_file)
                    new_row = pd.DataFrame([{'Date': pd.to_datetime(a_date), 'Vehicule': car, 'Kilometrage': a_km, 'Description': a_desc, 'Cout': a_prix, 'Facture': f_path}])
                    df_maint = pd.concat([df_maint, new_row], ignore_index=True); save_data(df_maint, "maintenance"); st.success("Ligne ajoutée !"); st.rerun()
        st.write("---")
        with st.expander("🔍 Filtres & Tri"):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                sort_col = st.selectbox("Trier par", ["Date", "Kilometrage", "Cout"], index=0)
                sort_asc = st.radio("Ordre", ["Décroissant ⬇️", "Croissant ⬆️"], index=0, horizontal=True)
            with col_t2: filter_date = st.date_input("Filtrer par date", [])

        df_edit_m = df_maint[df_maint['Vehicule'] == car].copy()
        is_filtered = False
        if len(filter_date) == 2: df_edit_m = df_edit_m[(df_edit_m['Date'].dt.date >= filter_date[0]) & (df_edit_m['Date'].dt.date <= filter_date[1])]; is_filtered = True
        asc = True if sort_asc == "Croissant ⬆️" else False
        df_edit_m = df_edit_m.sort_values(by=sort_col, ascending=asc)
        df_edit_m['Facture_Dispo'] = df_edit_m['Facture'].apply(lambda x: "📄 OUI" if x and str(x) != "None" and str(x) != "" else "")

        if is_filtered:
            st.warning("Mode Filtre (Lecture Seule).")
            st.dataframe(df_edit_m[['Date', 'Kilometrage', 'Description', 'Cout', 'Facture_Dispo']], use_container_width=True, hide_index=True)
        else:
            st.info("💡 Mode Édition. Clic sur ligne + Suppr pour effacer.")
            edited_m = st.data_editor(df_edit_m, num_rows="dynamic", use_container_width=True, hide_index=True, key="edit_m", column_config={"Date": st.column_config.DateColumn(format="DD/MM/YYYY"), "Cout": st.column_config.NumberColumn(format="%.2f €"), "Vehicule": st.column_config.Column(disabled=True), "Facture": st.column_config.Column(disabled=True), "Facture_Dispo": st.column_config.Column("Facture ?", disabled=True)})
            if st.button("💾 Sauvegarder Tableau", type="primary"):
                df_others = df_maint[df_maint['Vehicule'] != car]
                edited_m['Vehicule'] = car
                df_maint = pd.concat([df_others, edited_m.drop(columns=['Facture_Dispo'])], ignore_index=True); save_data(df_maint, "maintenance"); st.success("Mis à jour !"); st.rerun()

        st.write("---")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🖨️ Export Complet")
            if st.button("Générer Dossier PDF (Tableau + Factures)"):
                pdf = generer_pdf_complet(car, df_edit_m)
                with open(pdf, "rb") as f: st.download_button("📥 Télécharger le PDF Complet", f, file_name=pdf)
        with c2:
            st.subheader("📥 Télécharger une facture seule")
            facts = df_edit_m[['Date', 'Description', 'Facture']].dropna()
            facts = facts[(facts['Facture'] != "") & (facts['Facture'] != "None")]
            if not facts.empty:
                format_fact = st.selectbox("Choisir fichier", facts.index, format_func=lambda i: f"{facts.loc[i, 'Date'].strftime('%d/%m/%y')} - {facts.loc[i, 'Description']}")
                if format_fact is not None:
                    f_path = facts.loc[format_fact, 'Facture']
                    if os.path.exists(f_path):
                        with open(f_path, "rb") as f: st.download_button("Télécharger Fichier", f, file_name=os.path.basename(f_path))
            else: st.caption("Aucune facture.")

    with tab_f:
        df_edit_f = df_fuel[df_fuel['Vehicule'] == car].sort_values('Date', ascending=False)
        edited_f = st.data_editor(df_edit_f, num_rows="dynamic", use_container_width=True, hide_index=True, key="edit_f", column_config={"Date": st.column_config.DateColumn(format="DD/MM/YYYY"), "Vehicule": st.column_config.Column(disabled=True)})
        if st.button("💾 Sauvegarder Pleins", type="primary"):
            df_others = df_fuel[df_fuel['Vehicule'] != car]
            edited_f['Vehicule'] = car
            df_fuel = pd.concat([df_others, edited_f], ignore_index=True); save_data(df_fuel, "carburant"); st.success("OK"); st.rerun()

    with tab_a:
        st.subheader("⚠️ Alertes")
        messages = []
        vid = df_edit_m[df_edit_m['Description'].str.contains('vidange', case=False, na=False)]
        km_now = df_c['Kilometrage'].max() if not df_c.empty else 0
        if not vid.empty:
            diff = km_now - vid.iloc[0]['Kilometrage']
            if diff > 15000: m=f"URGENT: Vidange (+{diff-15000}km)"; st.error(m); messages.append(m)
            elif diff > 12000: m=f"PREVOIR: Vidange bientôt (+{diff}km)"; st.warning(m); messages.append(m)
            else: st.success(f"Vidange OK ({diff}km)")
        else: st.info("Pas d'historique vidange"); messages.append("Pas d'historique vidange.")
        st.write("---")
        sujet = f"Rapport - {car}"; corps = f"Etat {car} ({km_now}km):\n\n" + ("ALERTES:\n"+"\n".join(messages) if messages else "OK")
        lnk = f"mailto:?subject={urllib.parse.quote(sujet)}&body={urllib.parse.quote(corps)}"
        st.markdown(f"""<a href="{lnk}" class="email-btn" target="_blank">📧 Envoyer Rapport</a>""", unsafe_allow_html=True)