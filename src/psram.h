#pragma once

#include <stddef.h>
#include <stdbool.h>

/*
 * Print detailed PSRAM status
 */
void psram_print_status();

/*
 * Test PSRAM allocation with specific size (bytes)
 * return true if success
 */
bool psram_test_allocation(size_t bytes);

/*
 * Print heap summary (internal + spiram)
 */
void psram_print_heap_summary();
