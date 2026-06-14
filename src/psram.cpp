#include "psram.h"
#include <Arduino.h>
#include "esp_heap_caps.h"
#include "esp_system.h"

void psram_print_status()
{
    Serial.println("========== PSRAM STATUS ==========");

    if (psramFound())
        Serial.println("PSRAM Found       : YES");
    else
        Serial.println("PSRAM Found       : NO");

    size_t total_psram = ESP.getPsramSize();
    size_t free_psram = ESP.getFreePsram();

    Serial.printf("PSRAM Total       : %u bytes\n", total_psram);
    Serial.printf("PSRAM Free        : %u bytes\n", free_psram);

    size_t spiram_total = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    size_t spiram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);

    Serial.printf("Heap SPIRAM Total : %u bytes\n", spiram_total);
    Serial.printf("Heap SPIRAM Free  : %u bytes\n", spiram_free);

    Serial.println("==================================");
}

void psram_print_heap_summary()
{
    Serial.println("========== HEAP SUMMARY ==========");

    size_t internal_total = heap_caps_get_total_size(MALLOC_CAP_INTERNAL);
    size_t internal_free = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);

    size_t spiram_total = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    size_t spiram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);

    Serial.printf("Internal Total : %u bytes\n", internal_total);
    Serial.printf("Internal Free  : %u bytes\n", internal_free);

    Serial.printf("SPIRAM Total   : %u bytes\n", spiram_total);
    Serial.printf("SPIRAM Free    : %u bytes\n", spiram_free);

    Serial.println("==================================");
}

bool psram_test_allocation(size_t bytes)
{
    Serial.println("---------- PSRAM TEST ----------");
    Serial.printf("Testing allocation: %u bytes\n", bytes);

    void *ptr = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM);

    if (ptr)
    {
        Serial.println("Allocation SUCCESS (PSRAM)");
        heap_caps_free(ptr);
        return true;
    }
    else
    {
        Serial.println("Allocation FAILED (PSRAM)");
        return false;
    }
}
