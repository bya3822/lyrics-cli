
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	appName    = "lyrics-cli"
	appVersion = "0.1.0"
	baseURL    = "https://lrclib.net"
)

var timestampRegex = regexp.MustCompile(`^\[(\d+):(\d+(?:\.\d+)?)\](.*)$`)

type LRCLIBResult struct {
	TrackName    string  `json:"trackName"`
	ArtistName   string  `json:"artistName"`
	AlbumName    string  `json:"albumName"`
	Duration     float64 `json:"duration"`
	Instrumental bool    `json:"instrumental"`
	PlainLyrics  string  `json:"plainLyrics"`
	SyncedLyrics string  `json:"syncedLyrics"`
}

type LyricLine struct {
	Time float64 `json:"time"`
	Text string  `json:"text"`
}

type LyricsOutput struct {
	Title        string      `json:"title"`
	Artist       string      `json:"artist"`
	Album        string      `json:"album"`
	Duration     float64     `json:"duration"`
	Synced       bool        `json:"synced"`
	Lyrics       []LyricLine `json:"lyrics"`
	PlainLyrics  string      `json:"plainLyrics"`
	Instrumental bool        `json:"instrumental"`
}

func main() {
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds)
	log.SetOutput(os.Stderr)

	log.Println("[INFO] Iniciando lyrics-cli")

	if len(os.Args) < 3 {
		log.Println("[WARN] Argumentos insuficientes")
		fmt.Fprintf(os.Stderr, "Uso: %s \"titulo\" \"artista\"\n", os.Args[0])
		os.Exit(1)
	}

	title := os.Args[1]
	artist := os.Args[2]

	log.Printf("[INFO] Canción solicitada: %s - %s", artist, title)

	result, err := searchLRCLIB(title, artist)
	if err != nil {
		log.Printf("[ERROR] Búsqueda fallida: %v", err)
		os.Exit(1)
	}

	output := buildOutput(result)

	log.Println("[INFO] Generando JSON para el frontend")

	if err := json.NewEncoder(os.Stdout).Encode(output); err != nil {
		log.Printf("[ERROR] No se pudo generar el JSON: %v", err)
		os.Exit(1)
	}

	log.Println("[INFO] Datos enviados correctamente")
}

func searchLRCLIB(title, artist string) (*LRCLIBResult, error) {
	log.Printf("[DEBUG] Entrando en searchLRCLIB: %q - %q", artist, title)

	params := url.Values{}
	params.Set("q", title+" "+artist)

	endpoint := baseURL + "/api/search?" + params.Encode()

	log.Printf("[DEBUG] URL de búsqueda: %s", endpoint)

	body, err := requestLRCLIB(endpoint)
	if err != nil {
		log.Printf("[ERROR] searchLRCLIB: %v", err)
		return nil, err
	}

	var results []LRCLIBResult

	if err := json.Unmarshal(body, &results); err != nil {
		log.Printf("[ERROR] Error decodificando JSON: %v", err)
		return nil, err
	}

	log.Printf("[DEBUG] Resultados recibidos: %d", len(results))

	if len(results) == 0 {
		log.Println("[WARN] LRCLIB no encontró resultados")
		return nil, fmt.Errorf("no se encontraron resultados")
	}

	log.Printf("[INFO] Resultado seleccionado: %s - %s",
		results[0].ArtistName, results[0].TrackName)

	return &results[0], nil
}

func requestLRCLIB(endpoint string) ([]byte, error) {
	log.Println("[DEBUG] Entrando en requestLRCLIB")

	client := &http.Client{
		Timeout: 10 * time.Second,
	}

	req, err := http.NewRequest(http.MethodGet, endpoint, nil)
	if err != nil {
		log.Printf("[ERROR] No se pudo crear la petición: %v", err)
		return nil, err
	}

	req.Header.Set("User-Agent", appName+"/"+appVersion)

	log.Println("[DEBUG] Enviando petición HTTP a LRCLIB")

	resp, err := client.Do(req)
	if err != nil {
		log.Printf("[ERROR] Petición HTTP fallida: %v", err)
		return nil, err
	}
	defer resp.Body.Close()

	log.Printf("[INFO] Respuesta HTTP: %d", resp.StatusCode)

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("LRCLIB respondió con HTTP %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		log.Printf("[ERROR] No se pudo leer la respuesta: %v", err)
		return nil, err
	}

	log.Printf("[DEBUG] Respuesta recibida: %d bytes", len(body))

	return body, nil
}

func parseLRC(raw string) []LyricLine {
	log.Println("[DEBUG] Entrando en parseLRC")

	lines := []LyricLine{}

	for _, line := range strings.Split(raw, "\n") {
		line = strings.TrimSpace(line)

		match := timestampRegex.FindStringSubmatch(line)
		if match == nil {
			continue
		}

		minutes, err := strconv.Atoi(match[1])
		if err != nil {
			log.Printf("[WARN] Minutos inválidos: %s", match[1])
			continue
		}

		seconds, err := strconv.ParseFloat(match[2], 64)
		if err != nil {
			log.Printf("[WARN] Segundos inválidos: %s", match[2])
			continue
		}

		text := strings.TrimSpace(match[3])
		if text == "" {
			continue
		}

		totalTime := float64(minutes*60) + seconds

		lines = append(lines, LyricLine{
			Time: totalTime,
			Text: text,
		})
	}

	sort.Slice(lines, func(i, j int) bool {
		return lines[i].Time < lines[j].Time
	})

	log.Printf("[DEBUG] Líneas sincronizadas procesadas: %d", len(lines))

	return lines
}

func buildOutput(result *LRCLIBResult) LyricsOutput {
	log.Println("[DEBUG] Entrando en buildOutput")

	output := LyricsOutput{
		Title:        result.TrackName,
		Artist:       result.ArtistName,
		Album:        result.AlbumName,
		Duration:     result.Duration,
		Synced:       result.SyncedLyrics != "",
		PlainLyrics:  result.PlainLyrics,
		Instrumental: result.Instrumental,
		Lyrics:       []LyricLine{},
	}

	if output.Synced {
		output.Lyrics = parseLRC(result.SyncedLyrics)
	}

	log.Printf("[INFO] JSON preparado: %d líneas", len(output.Lyrics))

	return output
}

