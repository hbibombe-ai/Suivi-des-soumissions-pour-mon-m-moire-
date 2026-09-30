# =============================================================================
#  CARTE SANITAIRE DE LA ZS DE LIMETE -> fichier pour le tableau de bord
#
#  Transforme le shapefile des aires de santé (DSNIS/GRID3, dossier « Cartographie »
#  du mémoire) en un petit fichier GeoJSON contenant les 11 aires de la ZS de Limete,
#  avec les noms du formulaire KoboCollect.
#
#  Utilisation (une seule fois) :
#   1. Dans RStudio : Session > Set Working Directory > Choose Directory…
#      et choisir le dossier « Memoire Hardy BT » (celui qui contient « Cartographie »).
#   2. Ouvrir ce script et cliquer sur « Source ».
#   3. Copier le fichier créé, aires_limete.geojson, dans le dossier
#      carte_sanitaire/ du tableau de bord, puis l'envoyer sur GitHub.
#
#  Package : install.packages("sf")
# =============================================================================

library(sf)

# 1. Trouver et lire le shapefile des aires de santé -------------------------
shp <- list.files("Cartographie", pattern = "Aires.*\\.shp$", recursive = TRUE,
                  full.names = TRUE, ignore.case = TRUE)[1]
if (is.na(shp)) stop("Shapefile des aires de santé introuvable dans le dossier « Cartographie ».")
aires_rdc <- st_read(shp, quiet = TRUE)
cat("Fichier lu :", shp, "-", nrow(aires_rdc), "aires de santé\n")

# Noms des colonnes (DSNIS/GRID3 : « ZS » pour la zone, « AS_ » pour l'aire)
col_zs <- intersect(c("ZS", "Zone_Sante", "zs", "ZONE_SANTE"), names(aires_rdc))[1]
col_as <- intersect(c("AS_", "AS", "Aire_Sante", "aire", "AIRE_SANTE", "Nom"), names(aires_rdc))[1]
if (is.na(col_zs) || is.na(col_as)) {
  print(names(aires_rdc))
  stop("Colonnes de la zone ou de l'aire introuvables : indiquer leurs noms dans col_zs et col_as.")
}

# 2. Garder la ZS de Limete (équivalent du filtre QGIS "ZS" ILIKE '%limete%') ----
limete <- aires_rdc[grepl("limete", aires_rdc[[col_zs]], ignore.case = TRUE), ]
cat("Aires de la ZS de Limete :", nrow(limete), "\n")

# 3. Noms du formulaire (les noms officiels sont parfois différents) ---------
correspondance <- c("Industrielle 1" = "Industriel 1", "Industrielle 2" = "Industriel 2",
                    "Industrielle 3" = "Industriel 3", "Mfumu Mvula" = "Mfumu",
                    "Résidentielle" = "Résidentiel")
officiel <- trimws(as.character(limete[[col_as]]))
limete$nom_officiel <- officiel
limete$aire <- ifelse(officiel %in% names(correspondance), correspondance[officiel], officiel)
limete$zs <- "Limete"

aires_formulaire <- c("Agricole", "Industriel 1", "Industriel 2", "Industriel 3", "Masiala", "Mateba",
                      "Mayulu", "Mfumu", "Mombele", "Mososo", "Résidentiel")
manquantes <- setdiff(aires_formulaire, limete$aire)
en_trop <- setdiff(limete$aire, aires_formulaire)
if (length(manquantes)) message("Aires du formulaire absentes de la carte : ", paste(manquantes, collapse = ", "))
if (length(en_trop)) message("Aires de la carte absentes du formulaire (à ajouter à « correspondance ») : ",
                             paste(en_trop, collapse = ", "))

# 4. Coordonnées GPS (WGS 84) et contours légèrement simplifiés (5 m) --------
limete <- st_make_valid(limete)
limete <- st_transform(limete, 32733)            # UTM 33 Sud, en mètres
limete <- st_simplify(limete, dTolerance = 5, preserveTopology = TRUE)
limete <- st_transform(limete, 4326)             # latitude / longitude, comme le GPS de Kobo

# 5. Enregistrer -------------------------------------------------------------
sortie <- "aires_limete.geojson"
if (file.exists(sortie)) file.remove(sortie)
st_write(limete[, c("aire", "nom_officiel", "zs")], sortie, driver = "GeoJSON", quiet = TRUE,
         layer_options = c("RFC7946=YES", "COORDINATE_PRECISION=6"))
cat("Fichier créé :", normalizePath(sortie), "(", round(file.size(sortie) / 1024), "Ko )\n")
cat("À copier dans le dossier carte_sanitaire/ du tableau de bord.\n")
plot(st_geometry(limete), main = "Aires de santé de la ZS de Limete")
