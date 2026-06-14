#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "B674_SqueezeNetTiny_model.h"
#include "esp32_tflm_wrapper.h"

#define MODEL_NAME "B674_SqueezeNetTiny_model"

// Konfigurasi WiFi Rumah / Hotspot HP Anda
const char *ssid = "TP-LINK_8742";
const char *password = "14172182";

// URL Server PythonAnywhere Anda
const char *server_url = "http://robbydr.pythonanywhere.com/api/hama";

#define IMG_SIZE 96
#define IMG_BYTES (IMG_SIZE * IMG_SIZE)

#define ARENA_SIZE (118 * 1024)
#define TF_NUM_OPS 20

uint8_t image_buffer[IMG_BYTES];
int8_t input_tensor[IMG_BYTES];

Eloquent::TF::Sequential<TF_NUM_OPS, ARENA_SIZE> cnn;

uint32_t iteration = 0;
unsigned long last_heartbeat = 0;
const unsigned long HEARTBEAT_INTERVAL = 3600000; // 1 Jam dalam milidetik

// Fungsi Pembantu untuk Konversi Buffer Gambar ke Base64 (untuk dikirim via JSON)
String base64_encode(uint8_t *input, size_t input_len)
{
    static const char base64_chars[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    String output = "";
    int i = 0, j = 0;
    uint8_t char_array_3[3], char_array_4[4];

    while (input_len--)
    {
        char_array_3[i++] = *(input++);
        if (i == 3)
        {
            char_array_4[0] = (char_array_3[0] & 0xfc) >> 2;
            char_array_4[1] = ((char_array_3[0] & 0x03) << 4) + ((char_array_3[1] & 0xf0) >> 4);
            char_array_4[2] = ((char_array_3[1] & 0x0f) << 2) + ((char_array_3[2] & 0xc0) >> 6);
            char_array_4[3] = char_array_3[2] & 0x3f;
            for (i = 0; (i < 4); i++)
                output += base64_chars[char_array_4[i]];
            i = 0;
        }
    }
    if (i)
    {
        for (j = i; j < 3; j++)
            char_array_3[j] = '\0';
        char_array_4[0] = (char_array_3[0] & 0xfc) >> 2;
        char_array_4[1] = ((char_array_3[0] & 0x03) << 4) + ((char_array_3[1] & 0xf0) >> 4);
        char_array_4[2] = ((char_array_3[1] & 0x0f) << 2) + ((char_array_3[2] & 0xc0) >> 6);
        for (j = 0; (j < i + 1); j++)
            output += base64_chars[char_array_4[j]];
        while ((i++ < 3))
            output += '=';
    }
    return output;
}

// Fungsi untuk Mengirim Data JSON ke Server PythonAnywhere
void send_data_to_server(int pred, float confidence, uint32_t latency, uint32_t ram, String foto_b64)
{
    if (WiFi.status() == WL_CONNECTED)
    {
        HTTPClient http;
        http.begin(server_url);
        http.addHeader("Content-Type", "application/json");

        // Alokasikan memori JSON (ditambah kapasitas untuk menampung string gambar Base64)
        DynamicJsonDocument doc(IMG_BYTES * 2 + 500);
        doc["device_id"] = "ESP32S3_FIELD_01";
        doc["pred"] = pred;
        doc["confidence"] = confidence;
        doc["lat"] = latency;
        doc["arena"] = ARENA_SIZE;
        doc["ram"] = ram / 1024; // Konversi ke KB sesuai kebutuhan database
        doc["iter"] = iteration;
        doc["foto"] = foto_b64;

        String json_payload;
        serializeJson(doc, json_payload);

        int http_code = http.POST(json_payload);

        if (http_code > 0)
        {
            Serial.printf("[HTTP] POST Response Code: %d\n", http_code);
            String response = http.getString();
            Serial.println(response);
        }
        else
        {
            Serial.printf("[HTTP] POST Failed, error: %s\n", http.errorToString(http_code).c_str());
        }
        http.end();
    }
    else
    {
        Serial.println("WiFi Disconnected, gagal mengirim data.");
    }
}

void setup()
{
    Serial.begin(115200);
    delay(2000);

    Serial.println("ESP32 Benchmark + IoT Ready");

    // Koneksi ke WiFi Jaringan Rumah/Sawah
    WiFi.begin(ssid, password);
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi Connected!");

    // Konsep input output TFLM
    cnn.setNumInputs(IMG_BYTES);
    cnn.setNumOutputs(4);

    // REGISTER OPS GENERAL
    cnn.resolver.AddConv2D();
    cnn.resolver.AddFullyConnected();
    cnn.resolver.AddMaxPool2D();
    cnn.resolver.AddMean();
    cnn.resolver.AddSoftmax();
    cnn.resolver.AddDepthwiseConv2D();
    cnn.resolver.AddTranspose();
    cnn.resolver.AddReshape();
    cnn.resolver.AddConcatenation();
    cnn.resolver.AddHardSwish();
    cnn.resolver.AddMul();
    cnn.resolver.AddPack();
    cnn.resolver.AddShape();
    cnn.resolver.AddStridedSlice();
    cnn.resolver.AddAdd();
    cnn.resolver.AddAveragePool2D();
    cnn.resolver.AddQuantize();
    cnn.resolver.AddDequantize();

    // Init model
    while (!cnn.begin(B674_SqueezeNetTiny_model).isOk())
    {
        Serial.println(cnn.exception.toString());
        delay(1000);
    }

    Serial.print("Model loaded: ");
    Serial.println(MODEL_NAME);
}

void loop()
{
    // =======================================================
    // LOGIKA HEARTBEAT PERIODIK (Mengirim tanda hidup tiap 1 Jam)
    // =======================================================
    if (millis() - last_heartbeat >= HEARTBEAT_INTERVAL)
    {
        last_heartbeat = millis();
        uint32_t free_ram = ESP.getFreeHeap();
        Serial.println("Mengirim paket Heartbeat berkala...");
        // pred = 0 digunakan sebagai tanda Heartbeat aman (Tanpa Hama)
        send_data_to_server(0, 0.0, 0, free_ram, "");
    }

    // =======================================================
    // PROSES MENERIMA DATA GAMBAR DARI SIMULATOR PYTHON (0xAA)
    // =======================================================
    if (Serial.available() > 0)
    {
        if (Serial.read() == 0xAA)
        {
            // 1. Ambil 1 byte berikutnya sebagai Ground Truth CLASS (1-4)
            while (Serial.available() == 0)
                ; // Tunggu sampai byte kelas tiba
            int ground_truth_class = Serial.read();

            // 2. Baca biner gambar 96x96 (Persis 9216 bytes)
            // Timeout bawaan serial adalah 1 detik, cukup untuk mentransfer 9KB pada baud 115200
            size_t received = Serial.readBytes(image_buffer, IMG_BYTES);

            if (received != IMG_BYTES)
            {
                Serial.printf("Image size mismatch! Received: %d bytes\n", received);
                return;
            }

            iteration++;
            uint32_t start = millis();

            // 3. Normalisasi uint8 → int8 untuk input tensor TFLM
            for (int i = 0; i < IMG_BYTES; i++)
            {
                input_tensor[i] = (int8_t)image_buffer[i] - 128;
            }

            // 4. JALANKAN INFERENCE MODEL TINYNAS
            if (!cnn.predict(input_tensor).isOk())
            {
                Serial.println(cnn.exception.toString());
                return;
            }

            // Hasil Prediksi TFLM (0-3) kita konversi ke skala Class (1-4)
            int pred = cnn.classification + 1;
            uint32_t latency = millis() - start;
            uint32_t free_ram = ESP.getFreeHeap();

            // Ambil nilai confidence float (0.0 - 1.0)
            float confidence = 0.0;
            if (cnn.outputs != nullptr)
            {
                confidence = cnn.outputs[cnn.classification];
            }

            // HITUNG CORRECTNESS EVALUASI
            int correctness = (pred == ground_truth_class) ? 1 : 0;

            // 5. BALIKKAN FEEDBACK LENGKAP KE SIMULATOR PYTHON
            Serial.printf("CLASS:%d,PRED:%d,CORRECTNESS:%d,CONF:%.2f,LAT:%lu,ARENA:%d,RAM:%lu,ITER:%lu\n",
                          ground_truth_class, pred, correctness, confidence, latency, ARENA_SIZE, free_ram / 1024, iteration);

            // 6. ENCODE GAMBAR RAW TADI KE BASE64 & KIRIM KE SERVER CLOUD
            // Karena semua kelas 1-4 adalah Hama, kita selalu lampirkan gambarnya
            String foto_payload = base64_encode(image_buffer, IMG_BYTES);

            // Catatan: Parameter pred dikirim ke fungsi agar server mencatat hasil tebakan AI
            send_data_to_server(pred, confidence, latency, free_ram, foto_payload);

            last_heartbeat = millis();
        }
    }
}