/* lgpt_gater.c — gate rítmico mono sincronizado a BPM (LADSPA).
 *
 * Plugin propio para el rack de Carla del vocoder (ver vocoder/prod/
 * template01.carxp). Trocea la voz en un patrón de bloques sonido/silencio
 * sincronizado al compás, con la finura controlada por un solo knob.
 *
 * Ningún plugin LADSPA existente hacía esto: los tremolos/ring-mod no dan
 * silencio real en bloques sincronizados al compás y el único candidato
 * (ringmod_1188 en AM+square) tiene la frecuencia mínima en 1 Hz, con lo que
 * el patrón SM (medio compás a BPM normal ~0.5 Hz) es inalcanzable. Ver la
 * sección "Alternativas descartadas" del plan y README.md de este directorio.
 *
 * Puertos (el ORDEN fija los índices de parámetro que usa Carla por OSC):
 *   0 Input   audio in
 *   1 Output  audio out
 *   2 BPM      control in, 30..300  (default 120)  -> parámetro Carla 0
 *   3 Pattern  control in, 0..1     (default 0)    -> parámetro Carla 1
 *
 * Pattern (recorrido del knob dividido en 4 cuartos; S=suena, M=silencio;
 * unidad = un compás de BEATS_PER_BAR negras = 240/BPM s):
 *   [0.00,0.25) paso 1: passthrough (todo suena)
 *   [0.25,0.50) paso 2: SM      (compás en 2 porciones)
 *   [0.50,0.75) paso 3: SMSM    (4 porciones)
 *   [0.75,1.00] paso 4: SMSMSM  (6 porciones)
 * El compás se divide en 2*P porciones iguales (P = nº de pares del paso:
 * 1, 2, 3); las de índice par suenan y las impares se silencian.
 *
 * El BPM lo actualiza el vocoder por OSC (vocoder/flask/tcp_client.py), igual
 * que ya hace con el Calf Vintage Delay.
 */

#include <stdlib.h>
#include <math.h>

#include "ladspa.h"

#define GATER_UNIQUE_ID 1279874631UL   /* 0x4C475447 ("LGTG"), uso privado */

#define BEATS_PER_BAR   4              /* compás de 4 negras (4/4) */
#define FADE_MS         4.0f           /* rampa anti-clic en cada transición */

#define BPM_MIN         30.0f
#define BPM_MAX         300.0f

/* Índices de puerto */
enum {
    PORT_INPUT = 0,
    PORT_OUTPUT,
    PORT_BPM,
    PORT_PATTERN,
    PORT_COUNT
};

typedef struct {
    LADSPA_Data   sample_rate;

    LADSPA_Data  *in;        /* PORT_INPUT   */
    LADSPA_Data  *out;       /* PORT_OUTPUT  */
    LADSPA_Data  *bpm;       /* PORT_BPM     */
    LADSPA_Data  *pattern;   /* PORT_PATTERN */

    double        phase;         /* muestras transcurridas dentro del compás */
    float         gain;          /* ganancia suavizada actual (0..1) */

    /* Para detectar cambios y reiniciar la fase (arranque limpio del patrón). */
    float         last_bpm;
    int           last_step;
} Gater;

static LADSPA_Handle instantiate(const LADSPA_Descriptor *desc,
                                 unsigned long sample_rate) {
    (void)desc;
    Gater *g = (Gater *)calloc(1, sizeof(Gater));
    if (g == NULL)
        return NULL;
    g->sample_rate = (LADSPA_Data)sample_rate;
    g->phase = 0.0;
    g->gain = 1.0f;
    g->last_bpm = -1.0f;
    g->last_step = -1;
    return (LADSPA_Handle)g;
}

static void connect_port(LADSPA_Handle handle, unsigned long port,
                         LADSPA_Data *data) {
    Gater *g = (Gater *)handle;
    switch (port) {
        case PORT_INPUT:   g->in = data;      break;
        case PORT_OUTPUT:  g->out = data;     break;
        case PORT_BPM:     g->bpm = data;     break;
        case PORT_PATTERN: g->pattern = data; break;
        default: break;
    }
}

static void activate(LADSPA_Handle handle) {
    Gater *g = (Gater *)handle;
    g->phase = 0.0;
    g->gain = 1.0f;
    g->last_bpm = -1.0f;
    g->last_step = -1;
}

static void run(LADSPA_Handle handle, unsigned long sample_count) {
    Gater *g = (Gater *)handle;
    const LADSPA_Data *in = g->in;
    LADSPA_Data *out = g->out;

    /* BPM válido y acotado (fuera de rango o inválido -> passthrough). */
    float bpm = (g->bpm != NULL) ? *g->bpm : 120.0f;
    if (!(bpm > 0.0f))
        bpm = 120.0f;
    if (bpm < BPM_MIN) bpm = BPM_MIN;
    if (bpm > BPM_MAX) bpm = BPM_MAX;

    /* Knob -> paso (0..3). Paso 0 = passthrough; P = nº de pares. */
    float p = (g->pattern != NULL) ? *g->pattern : 0.0f;
    if (p < 0.0f) p = 0.0f;
    if (p > 1.0f) p = 1.0f;
    int step = (int)(p * 4.0f);
    if (step > 3) step = 3;              /* p == 1.0 cae en el paso 4 */

    /* Reiniciar la fase al cambiar de tempo o de paso: así el patrón arranca
     * siempre en S justo cuando el intérprete gira el knob o cambia el tema. */
    if (bpm != g->last_bpm || step != g->last_step) {
        g->phase = 0.0;
        g->last_bpm = bpm;
        g->last_step = step;
    }

    const double measure = (double)BEATS_PER_BAR * 60.0 / (double)bpm
                           * (double)g->sample_rate;      /* muestras/compás */
    const int slices = 2 * step;                          /* 0 si passthrough */
    const double slice_len = (slices > 0) ? measure / (double)slices : measure;

    /* Paso de rampa por muestra hacia el objetivo (anti-clic). */
    float fade_samples = FADE_MS * 0.001f * g->sample_rate;
    if (fade_samples < 1.0f) fade_samples = 1.0f;
    const float gain_step = 1.0f / fade_samples;

    for (unsigned long i = 0; i < sample_count; i++) {
        float target;
        if (slices == 0) {
            target = 1.0f;                                /* passthrough */
        } else {
            int slot = (int)(g->phase / slice_len) % slices;
            target = (slot % 2 == 0) ? 1.0f : 0.0f;       /* par=S, impar=M */
        }

        if (g->gain < target) {
            g->gain += gain_step;
            if (g->gain > target) g->gain = target;
        } else if (g->gain > target) {
            g->gain -= gain_step;
            if (g->gain < target) g->gain = target;
        }

        out[i] = in[i] * g->gain;

        g->phase += 1.0;
        if (g->phase >= measure)
            g->phase -= measure;
    }
}

static void cleanup(LADSPA_Handle handle) {
    free(handle);
}

/* ---- Descriptor ---------------------------------------------------------- */

static LADSPA_Descriptor *g_descriptor = NULL;

static const char *const port_names[PORT_COUNT] = {
    "Input", "Output", "BPM", "Pattern"
};

static const LADSPA_PortDescriptor port_descriptors[PORT_COUNT] = {
    LADSPA_PORT_INPUT  | LADSPA_PORT_AUDIO,
    LADSPA_PORT_OUTPUT | LADSPA_PORT_AUDIO,
    LADSPA_PORT_INPUT  | LADSPA_PORT_CONTROL,
    LADSPA_PORT_INPUT  | LADSPA_PORT_CONTROL,
};

static const LADSPA_PortRangeHint port_range_hints[PORT_COUNT] = {
    { 0, 0.0f, 0.0f },                                   /* Input  */
    { 0, 0.0f, 0.0f },                                   /* Output */
    {   LADSPA_HINT_BOUNDED_BELOW | LADSPA_HINT_BOUNDED_ABOVE
      | LADSPA_HINT_DEFAULT_MIDDLE, BPM_MIN, BPM_MAX },  /* BPM 30..300, def 120 */
    {   LADSPA_HINT_BOUNDED_BELOW | LADSPA_HINT_BOUNDED_ABOVE
      | LADSPA_HINT_DEFAULT_MINIMUM, 0.0f, 1.0f },       /* Pattern 0..1, def 0 */
};

/* GCC: construir/destruir el descriptor al cargar/descargar la .so. */
static void __attribute__((constructor)) init(void) {
    g_descriptor = (LADSPA_Descriptor *)malloc(sizeof(LADSPA_Descriptor));
    if (g_descriptor == NULL)
        return;
    g_descriptor->UniqueID = GATER_UNIQUE_ID;
    g_descriptor->Label = "lgpt_gater";
    g_descriptor->Properties = LADSPA_PROPERTY_HARD_RT_CAPABLE;
    g_descriptor->Name = "LGPT Gater";
    g_descriptor->Maker = "lgptclient";
    g_descriptor->Copyright = "None";
    g_descriptor->PortCount = PORT_COUNT;
    g_descriptor->PortDescriptors = port_descriptors;
    g_descriptor->PortNames = port_names;
    g_descriptor->PortRangeHints = port_range_hints;
    g_descriptor->ImplementationData = NULL;
    g_descriptor->instantiate = instantiate;
    g_descriptor->connect_port = connect_port;
    g_descriptor->activate = activate;
    g_descriptor->run = run;
    g_descriptor->run_adding = NULL;
    g_descriptor->set_run_adding_gain = NULL;
    g_descriptor->deactivate = NULL;
    g_descriptor->cleanup = cleanup;
}

static void __attribute__((destructor)) fini(void) {
    free(g_descriptor);
    g_descriptor = NULL;
}

const LADSPA_Descriptor *ladspa_descriptor(unsigned long index) {
    return (index == 0) ? g_descriptor : NULL;
}
