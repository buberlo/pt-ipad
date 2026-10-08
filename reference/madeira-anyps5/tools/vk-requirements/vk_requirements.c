/* SPDX-License-Identifier: MIT */
/* Copyright (C) 2026 buberlo */
/* Report whether a Vulkan device meets AnyPS5's hard requirements.
 *
 * Derived from boykopovar/AnyPS5 (pinned in this repo) :
 *   core/libs/prx/libSceAgcDriver/Execution/src/VulkanDevice.cpp
 *   core/libs/prx/libSceAgcDriver/Execution/src/BdaFeatures.cpp
 *
 * Hard checks are the ones that throw before vkCreateDevice returns.
 * Optional checks are features AnyPS5 enables when the device has them
 * and otherwise runs without. This tool does not link AnyPS5.
 *
 * Exit status: 0 every hard check passed on the selected device,
 *              1 a hard check failed,
 *              2 the loader or instance could not be created,
 *              3 no Vulkan 1.1 graphics+compute device.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>

/* Ubuntu 22.04 ships Vulkan headers 1.3.204. Those headers have no
 * VK_KHR_portability_enumeration names. The string is the spec name, so
 * a newer loader that advertises the extension still matches. The
 * enumerate bit is applied only when that advertisement is present. */
#ifndef VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME
#define VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME "VK_KHR_portability_enumeration"
#endif
#ifndef VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR
#define VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR ((VkInstanceCreateFlags)0x00000001)
#endif

static int g_hard_fail;
static int g_optional_miss;
static int g_present;

static void hard(const char *name, int ok, const char *detail)
{
    printf("HARD  %-44s %s%s%s\n", name, ok ? "PASS" : "FAIL", detail ? "  " : "", detail ? detail : "");
    if (!ok) g_hard_fail++;
}

static void optional(const char *name, int ok)
{
    printf("OPT   %-44s %s\n", name, ok ? "present" : "absent");
    if (!ok) g_optional_miss++;
}

static void note(const char *name, const char *text)
{
    printf("NOTE  %-44s %s\n", name, text);
}

static int has_ext(const VkExtensionProperties *list, uint32_t count, const char *name)
{
    for (uint32_t i = 0; i < count; i++) {
        if (strcmp(list[i].extensionName, name) == 0) return 1;
    }
    return 0;
}

static void print_api(const char *label, uint32_t v)
{
    printf("%s %u.%u.%u\n", label, VK_API_VERSION_MAJOR(v), VK_API_VERSION_MINOR(v), VK_API_VERSION_PATCH(v));
}

static int rank_type(VkPhysicalDeviceType type)
{
    switch (type) {
    case VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU: return 3;
    case VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU: return 2;
    case VK_PHYSICAL_DEVICE_TYPE_VIRTUAL_GPU: return 1;
    default: return 0;
    }
}

static const char *type_name(VkPhysicalDeviceType type)
{
    switch (type) {
    case VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU: return "discrete";
    case VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU: return "integrated";
    case VK_PHYSICAL_DEVICE_TYPE_VIRTUAL_GPU: return "virtual";
    case VK_PHYSICAL_DEVICE_TYPE_CPU: return "cpu";
    default: return "other";
    }
}

static VkExtensionProperties *device_exts(VkPhysicalDevice physical, uint32_t *count)
{
    *count = 0;
    if (vkEnumerateDeviceExtensionProperties(physical, NULL, count, NULL) != VK_SUCCESS) return NULL;
    VkExtensionProperties *list = calloc(*count ? *count : 1, sizeof(*list));
    if (!list) return NULL;
    if (*count && vkEnumerateDeviceExtensionProperties(physical, NULL, count, list) != VK_SUCCESS) {
        free(list);
        return NULL;
    }
    return list;
}

static int queue_ok(VkPhysicalDevice physical, uint32_t *family_out)
{
    uint32_t families = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &families, NULL);
    if (!families) return 0;
    VkQueueFamilyProperties *queues = calloc(families, sizeof(*queues));
    if (!queues) return 0;
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &families, queues);
    int found = 0;
    for (uint32_t i = 0; i < families; i++) {
        const VkQueueFlags need = VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT;
        if (queues[i].queueCount && (queues[i].queueFlags & need) == need) {
            *family_out = i;
            found = 1;
            break;
        }
    }
    free(queues);
    return found;
}

static void check_device(VkPhysicalDevice physical, VkPhysicalDeviceProperties props)
{
    uint32_t ext_count = 0;
    VkExtensionProperties *exts = device_exts(physical, &ext_count);
    if (!exts) {
        hard("enumerate device extensions", 0, "vkEnumerateDeviceExtensionProperties failed");
        return;
    }

    VkPhysicalDeviceFeatures2 features = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2};
    VkPhysicalDevice8BitStorageFeatures storage8 = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_8BIT_STORAGE_FEATURES};
    VkPhysicalDeviceBufferDeviceAddressFeatures bda = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_BUFFER_DEVICE_ADDRESS_FEATURES};
    VkPhysicalDeviceTimelineSemaphoreFeatures timeline = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_TIMELINE_SEMAPHORE_FEATURES};
    VkPhysicalDeviceShaderClockFeaturesKHR clock = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_CLOCK_FEATURES_KHR};
    VkPhysicalDeviceDescriptorIndexingFeatures indexing = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DESCRIPTOR_INDEXING_FEATURES};
    /* Mesh-shader EXT and fragment-shader barycentric KHR arrived after
     * the headers in Ubuntu 22.04. They are optional AnyPS5 features.
     * Leave them off the pNext chain when the header cannot name them. */
#ifdef VK_EXT_MESH_SHADER_EXTENSION_NAME
    VkPhysicalDeviceMeshShaderFeaturesEXT mesh = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_MESH_SHADER_FEATURES_EXT};
#endif
#ifdef VK_KHR_FRAGMENT_SHADER_BARYCENTRIC_EXTENSION_NAME
    VkPhysicalDeviceFragmentShaderBarycentricFeaturesKHR bary = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FRAGMENT_SHADER_BARYCENTRIC_FEATURES_KHR};
#endif
    features.pNext = &storage8;
    storage8.pNext = &bda;
    bda.pNext = &timeline;
#ifdef VK_EXT_MESH_SHADER_EXTENSION_NAME
    timeline.pNext = &mesh;
#ifdef VK_KHR_FRAGMENT_SHADER_BARYCENTRIC_EXTENSION_NAME
    mesh.pNext = &bary;
    bary.pNext = &clock;
#else
    mesh.pNext = &clock;
#endif
#elif defined(VK_KHR_FRAGMENT_SHADER_BARYCENTRIC_EXTENSION_NAME)
    timeline.pNext = &bary;
    bary.pNext = &clock;
#else
    timeline.pNext = &clock;
#endif
    clock.pNext = &indexing;
    vkGetPhysicalDeviceFeatures2(physical, &features);

    VkPhysicalDeviceProperties2 properties2 = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};
    VkPhysicalDeviceFloatControlsProperties floats = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FLOAT_CONTROLS_PROPERTIES};
    properties2.pNext = &floats;
    vkGetPhysicalDeviceProperties2(physical, &properties2);

    const int api_ok = props.apiVersion >= VK_API_VERSION_1_1;
    char api_buf[64];
    snprintf(api_buf, sizeof api_buf, "%u.%u.%u", VK_API_VERSION_MAJOR(props.apiVersion),
             VK_API_VERSION_MINOR(props.apiVersion), VK_API_VERSION_PATCH(props.apiVersion));
    hard("Vulkan >= 1.1", api_ok, api_buf);

    hard("VK_KHR_8bit_storage", has_ext(exts, ext_count, VK_KHR_8BIT_STORAGE_EXTENSION_NAME), NULL);
    hard("storageBuffer8BitAccess", storage8.storageBuffer8BitAccess == VK_TRUE, NULL);
    hard("VK_KHR_buffer_device_address", has_ext(exts, ext_count, VK_KHR_BUFFER_DEVICE_ADDRESS_EXTENSION_NAME), NULL);
    hard("bufferDeviceAddress", bda.bufferDeviceAddress == VK_TRUE, NULL);
    hard("shaderInt64", features.features.shaderInt64 == VK_TRUE, NULL);
    hard("VK_KHR_shader_float_controls", has_ext(exts, ext_count, VK_KHR_SHADER_FLOAT_CONTROLS_EXTENSION_NAME), NULL);
    hard("shaderSignedZeroInfNanPreserveFloat32", floats.shaderSignedZeroInfNanPreserveFloat32 == VK_TRUE, NULL);
    hard("vertexPipelineStoresAndAtomics", features.features.vertexPipelineStoresAndAtomics == VK_TRUE, NULL);
    hard("fragmentStoresAndAtomics", features.features.fragmentStoresAndAtomics == VK_TRUE, NULL);
    hard("samplerAnisotropy", features.features.samplerAnisotropy == VK_TRUE, NULL);
    hard("textureCompressionBC", features.features.textureCompressionBC == VK_TRUE, NULL);
    if (g_present) {
        hard("VK_KHR_swapchain", has_ext(exts, ext_count, VK_KHR_SWAPCHAIN_EXTENSION_NAME),
             "extension only; no surface was created");
    } else {
        note("VK_KHR_swapchain", has_ext(exts, ext_count, VK_KHR_SWAPCHAIN_EXTENSION_NAME)
                                     ? "present (not required without a window)"
                                     : "absent (not required without a window)");
    }

#ifdef VK_EXT_MESH_SHADER_EXTENSION_NAME
    const int mesh_ext = has_ext(exts, ext_count, VK_EXT_MESH_SHADER_EXTENSION_NAME)
        && has_ext(exts, ext_count, VK_KHR_SPIRV_1_4_EXTENSION_NAME);
    optional("mesh shader (EXT_mesh_shader + SPIR-V 1.4)", mesh_ext && mesh.meshShader);
#else
    optional("mesh shader (EXT_mesh_shader + SPIR-V 1.4)", 0);
#endif
#ifdef VK_KHR_FRAGMENT_SHADER_BARYCENTRIC_EXTENSION_NAME
    optional("fragment shader barycentric", has_ext(exts, ext_count, VK_KHR_FRAGMENT_SHADER_BARYCENTRIC_EXTENSION_NAME) && bary.fragmentShaderBarycentric);
#else
    optional("fragment shader barycentric", 0);
#endif
    optional("shader clock (subgroup and device)", has_ext(exts, ext_count, VK_KHR_SHADER_CLOCK_EXTENSION_NAME)
             && clock.shaderSubgroupClock && clock.shaderDeviceClock);
    optional("VK_EXT_depth_range_unrestricted", has_ext(exts, ext_count, VK_EXT_DEPTH_RANGE_UNRESTRICTED_EXTENSION_NAME));
    optional("VK_EXT_image_robustness", has_ext(exts, ext_count, VK_EXT_IMAGE_ROBUSTNESS_EXTENSION_NAME));
    optional("VK_KHR_draw_indirect_count", has_ext(exts, ext_count, VK_KHR_DRAW_INDIRECT_COUNT_EXTENSION_NAME));
    optional("VK_EXT_external_memory_host", has_ext(exts, ext_count, VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME));
    optional("VK_EXT_primitive_topology_list_restart", has_ext(exts, ext_count, VK_EXT_PRIMITIVE_TOPOLOGY_LIST_RESTART_EXTENSION_NAME));
    optional("VK_EXT_image_view_min_lod", has_ext(exts, ext_count, VK_EXT_IMAGE_VIEW_MIN_LOD_EXTENSION_NAME));
    optional("VK_KHR_maintenance8", has_ext(exts, ext_count, "VK_KHR_maintenance8"));
    optional("VK_EXT_depth_clip_control", has_ext(exts, ext_count, VK_EXT_DEPTH_CLIP_CONTROL_EXTENSION_NAME));
    optional("timeline semaphores", has_ext(exts, ext_count, VK_KHR_TIMELINE_SEMAPHORE_EXTENSION_NAME) && timeline.timelineSemaphore);
    optional("descriptor indexing (nonuniform images)",
             has_ext(exts, ext_count, VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME)
                 && indexing.shaderSampledImageArrayNonUniformIndexing
                 && indexing.shaderStorageImageArrayNonUniformIndexing);
    optional("tessellationShader", features.features.tessellationShader);
    optional("shaderFloat64 + preserve Float64", features.features.shaderFloat64 && floats.shaderSignedZeroInfNanPreserveFloat64);
    optional("robustBufferAccess", features.features.robustBufferAccess);
    optional("drawIndirectFirstInstance", features.features.drawIndirectFirstInstance);
    optional("multiDrawIndirect", features.features.multiDrawIndirect);
    optional("depthClamp", features.features.depthClamp);
    optional("depthBounds", features.features.depthBounds);
    optional("depthBiasClamp", features.features.depthBiasClamp);
    optional("occlusionQueryPrecise", features.features.occlusionQueryPrecise);
    optional("shaderStorageImageWriteWithoutFormat", features.features.shaderStorageImageWriteWithoutFormat);
    optional("shaderStorageImageReadWithoutFormat", features.features.shaderStorageImageReadWithoutFormat);
    optional("shaderImageGatherExtended", features.features.shaderImageGatherExtended);
    optional("dynamic image array indexing", features.features.shaderSampledImageArrayDynamicIndexing
             && features.features.shaderStorageImageArrayDynamicIndexing);

    const int portability = has_ext(exts, ext_count, "VK_KHR_portability_subset");
    note("VK_KHR_portability_subset", portability
                                          ? "device requires AnyPS5 to enable it (patch 0002)"
                                          : "not a portability-subset device");
    free(exts);
}

static const char *vk_result_str(VkResult result)
{
    switch (result) {
    case VK_SUCCESS: return "VK_SUCCESS";
    case VK_ERROR_OUT_OF_HOST_MEMORY: return "VK_ERROR_OUT_OF_HOST_MEMORY";
    case VK_ERROR_OUT_OF_DEVICE_MEMORY: return "VK_ERROR_OUT_OF_DEVICE_MEMORY";
    case VK_ERROR_INITIALIZATION_FAILED: return "VK_ERROR_INITIALIZATION_FAILED";
    case VK_ERROR_LAYER_NOT_PRESENT: return "VK_ERROR_LAYER_NOT_PRESENT";
    case VK_ERROR_EXTENSION_NOT_PRESENT: return "VK_ERROR_EXTENSION_NOT_PRESENT";
    case VK_ERROR_INCOMPATIBLE_DRIVER: return "VK_ERROR_INCOMPATIBLE_DRIVER";
    default: return "other";
    }
}

static VkResult create_instance(const VkInstanceCreateInfo *info, VkInstance *instance)
{
    *instance = VK_NULL_HANDLE;
    return vkCreateInstance(info, NULL, instance);
}

static uint32_t device_count(VkInstance instance)
{
    uint32_t count = 0;
    if (vkEnumeratePhysicalDevices(instance, &count, NULL) != VK_SUCCESS) return 0;
    return count;
}

int main(int argc, char **argv)
{
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--present") == 0) g_present = 1;
        else if (strcmp(argv[i], "--help") == 0) {
            fprintf(stderr, "usage: %s [--present]\n", argv[0]);
            fprintf(stderr, "  --present   also require VK_KHR_swapchain (AnyPS5 does, when a window is passed)\n");
            return 2;
        } else {
            fprintf(stderr, "unknown argument: %s\n", argv[i]);
            return 2;
        }
    }

    uint32_t inst_ext_count = 0;
    if (vkEnumerateInstanceExtensionProperties(NULL, &inst_ext_count, NULL) != VK_SUCCESS) {
        fprintf(stderr, "vkEnumerateInstanceExtensionProperties failed (is a Vulkan loader installed?)\n");
        return 2;
    }
    VkExtensionProperties *inst_exts = calloc(inst_ext_count ? inst_ext_count : 1, sizeof(*inst_exts));
    if (!inst_exts) return 2;
    if (inst_ext_count && vkEnumerateInstanceExtensionProperties(NULL, &inst_ext_count, inst_exts) != VK_SUCCESS) {
        free(inst_exts);
        return 2;
    }
    const int have_portability_enum = has_ext(inst_exts, inst_ext_count, VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME);
    /* The metal surface extension is declared in vulkan_metal.h, which the
     * desktop vulkan.h does not pull in. The string is the extension name. */
    const int have_metal = has_ext(inst_exts, inst_ext_count, "VK_EXT_metal_surface");
    free(inst_exts);

    VkApplicationInfo app = {
        .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "anyps5-ipad vk-requirements",
        .apiVersion = VK_API_VERSION_1_1,
    };
    VkInstanceCreateInfo stock_info = {
        .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &app,
    };
    note("VK_EXT_metal_surface", have_metal ? "instance extension present" : "absent on this host");
    note("VK_KHR_portability_enumeration", have_portability_enum ? "instance extension present" : "absent on this host");

    /* Stock AnyPS5 does not set ENUMERATE_PORTABILITY. MoltenVK's only ICD
     * is a portability driver, and that create fails before any device
     * exists. When the enumeration extension is advertised, keep going and
     * record a stock device count of 0. A full ICD (lavapipe) still takes
     * the stock instance. */
    VkInstance stock = VK_NULL_HANDLE;
    const VkResult stock_result = create_instance(&stock_info, &stock);
    uint32_t stock_devices = 0;
    if (stock) {
        stock_devices = device_count(stock);
    } else {
        fprintf(stderr, "vkCreateInstance failed: %s (%d)\n", vk_result_str(stock_result), (int)stock_result);
        if (!have_portability_enum) return 2;
        note("stock instance", "create failed; continuing with portability enumeration");
    }
    printf("stock-anyps5-device-count %u\n", stock_devices);

    const char *port_exts[] = {VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME};
    VkInstanceCreateInfo port_info = stock_info;
    if (have_portability_enum) {
        port_info.flags = VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
        port_info.enabledExtensionCount = 1;
        port_info.ppEnabledExtensionNames = port_exts;
    }
    VkInstance instance = VK_NULL_HANDLE;
    if (have_portability_enum) {
        const VkResult port_result = create_instance(&port_info, &instance);
        if (!instance) {
            fprintf(stderr, "vkCreateInstance (portability) failed: %s (%d)\n",
                    vk_result_str(port_result), (int)port_result);
            if (stock) vkDestroyInstance(stock, NULL);
            return 2;
        }
    } else {
        instance = stock;
    }
    const uint32_t port_devices = device_count(instance);
    printf("portability-device-count %u\n", port_devices);
    if (port_devices != stock_devices) {
        note("portability gap", "stock AnyPS5 (no enumerate bit) does not see every device");
    }

    uint32_t count = 0;
    vkEnumeratePhysicalDevices(instance, &count, NULL);
    if (!count) {
        printf("summary hard_fail=0 optional_missing=0 selected=none\n");
        fprintf(stderr, "no physical devices\n");
        if (instance != stock) vkDestroyInstance(instance, NULL);
        vkDestroyInstance(stock, NULL);
        return 3;
    }
    VkPhysicalDevice *devices = calloc(count, sizeof(*devices));
    vkEnumeratePhysicalDevices(instance, &count, devices);

    VkPhysicalDevice selected = VK_NULL_HANDLE;
    VkPhysicalDeviceProperties selected_props;
    memset(&selected_props, 0, sizeof selected_props);
    int selected_rank = -1;
    uint32_t selected_family = 0;
    for (uint32_t i = 0; i < count; i++) {
        VkPhysicalDeviceProperties props;
        vkGetPhysicalDeviceProperties(devices[i], &props);
        uint32_t family = 0;
        const int q = queue_ok(devices[i], &family);
        printf("device[%u] %s type=%s api=%u.%u.%u graphics+compute=%s\n", i, props.deviceName, type_name(props.deviceType),
               VK_API_VERSION_MAJOR(props.apiVersion), VK_API_VERSION_MINOR(props.apiVersion), VK_API_VERSION_PATCH(props.apiVersion),
               q ? "yes" : "no");
        if (props.apiVersion < VK_API_VERSION_1_1 || !q) continue;
        if (g_present) {
            uint32_t ext_count = 0;
            VkExtensionProperties *exts = device_exts(devices[i], &ext_count);
            const int swap = exts && has_ext(exts, ext_count, VK_KHR_SWAPCHAIN_EXTENSION_NAME);
            free(exts);
            if (!swap) continue;
        }
        const int rank = rank_type(props.deviceType);
        if (rank <= selected_rank) continue;
        selected = devices[i];
        selected_props = props;
        selected_rank = rank;
        selected_family = family;
    }
    free(devices);

    if (!selected) {
        printf("summary hard_fail=0 optional_missing=0 selected=none\n");
        if (instance != stock) vkDestroyInstance(instance, NULL);
        vkDestroyInstance(stock, NULL);
        return 3;
    }

    printf("selected %s queue_family=%u\n", selected_props.deviceName, selected_family);
    print_api("selected-api", selected_props.apiVersion);
    check_device(selected, selected_props);
    printf("summary hard_fail=%d optional_missing=%d selected=%s\n", g_hard_fail, g_optional_miss, selected_props.deviceName);

    if (instance != stock) vkDestroyInstance(instance, NULL);
    vkDestroyInstance(stock, NULL);
    return g_hard_fail ? 1 : 0;
}
