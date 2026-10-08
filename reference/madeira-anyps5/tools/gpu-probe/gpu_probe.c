/* SPDX-License-Identifier: MIT */
/* Copyright (C) 2026 buberlo */
#include "gpu_probe.h"
#include <vulkan/vulkan.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

typedef struct {
    VkInstance instance;
    VkPhysicalDevice physical;
    VkDevice device;
    VkQueue queue;
    uint32_t family;
    VkCommandPool pool;
    FILE *report;
} Probe;
typedef struct { VkBuffer buffer; VkDeviceMemory memory; void *mapped; } Buffer;

static void result(Probe *p, const char *test, int ok, long code) {
    fprintf(p->report, "{\"schema\":1,\"stage\":\"native_gpu\",\"test\":\"%s\",\"status\":\"%s\",\"code\":%ld}\n",
            test, ok ? "pass" : "fail", code);
    fflush(p->report);
}
static void json_string(FILE *out, const char *s) {
    fputc('"', out);
    for (; *s; ++s) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') { fputc('\\', out); fputc(c, out); }
        else if (c < 32) fprintf(out, "\\u%04x", c);
        else fputc(c, out);
    }
    fputc('"', out);
}
static int extension(const VkExtensionProperties *items, uint32_t count, const char *name) {
    for (uint32_t i = 0; i < count; ++i) if (!strcmp(items[i].extensionName, name)) return 1;
    return 0;
}
/* Capability queries are evidence of support, not an MSAA execution test. */
static void sample_capabilities(Probe *p, const VkPhysicalDeviceProperties *props) {
    const VkPhysicalDeviceLimits *l = &props->limits;
    fprintf(p->report, "{\"schema\":1,\"stage\":\"native_gpu\",\"capability\":\"sample_count_limits\","
            "\"color_mask\":%u,\"depth_mask\":%u,\"stencil_mask\":%u,\"no_attachment_mask\":%u}\n",
            l->framebufferColorSampleCounts, l->framebufferDepthSampleCounts,
            l->framebufferStencilSampleCounts, l->framebufferNoAttachmentsSampleCounts);
    const struct { VkFormat format; VkImageUsageFlags usage; const char *name; } cases[] = {
        {VK_FORMAT_R8G8B8A8_UNORM, VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT, "rgba8_unorm"},
        {VK_FORMAT_R8G8B8A8_SRGB, VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT, "rgba8_srgb"},
        {VK_FORMAT_B8G8R8A8_UNORM, VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT, "bgra8_unorm"},
        {VK_FORMAT_R16G16B16A16_SFLOAT, VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT, "rgba16_float"},
        {VK_FORMAT_D16_UNORM_S8_UINT, VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT, "d16_s8"},
        {VK_FORMAT_D32_SFLOAT_S8_UINT, VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT, "d32_s8"},
        {VK_FORMAT_D32_SFLOAT, VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT, "d32"},
    };
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        VkImageFormatProperties image = {0};
        const VkResult rc = vkGetPhysicalDeviceImageFormatProperties(p->physical, cases[i].format,
            VK_IMAGE_TYPE_2D, VK_IMAGE_TILING_OPTIMAL, cases[i].usage, 0, &image);
        fprintf(p->report, "{\"schema\":1,\"stage\":\"native_gpu\",\"capability\":\"image_sample_counts\","
                "\"format\":\"%s\",\"vk_format\":%u,\"usage\":%u,\"code\":%ld,\"sample_mask\":%u}\n",
                cases[i].name, (unsigned)cases[i].format, cases[i].usage, (long)rc,
                rc == VK_SUCCESS ? image.sampleCounts : 0u);
    }
    fflush(p->report);
}
static VkResult initialize(Probe *p) {
    uint32_t count = 0;
    VkResult rc = vkEnumerateInstanceExtensionProperties(NULL, &count, NULL);
    if (rc != VK_SUCCESS) return rc;
    VkExtensionProperties *exts = calloc(count ? count : 1, sizeof(*exts));
    if (!exts) return VK_ERROR_OUT_OF_HOST_MEMORY;
    rc = vkEnumerateInstanceExtensionProperties(NULL, &count, exts);
    int portable = extension(exts, count, "VK_KHR_portability_enumeration");
    free(exts);
    if (rc != VK_SUCCESS) return rc;
    const char *instance_exts[] = {"VK_KHR_portability_enumeration"};
    VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "AnyPS5 hardware probe", .apiVersion = VK_API_VERSION_1_1};
    VkInstanceCreateInfo info = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
        .pApplicationInfo = &app, .enabledExtensionCount = portable ? 1 : 0,
        .ppEnabledExtensionNames = instance_exts, .flags = portable ? 1 : 0};
    rc = vkCreateInstance(&info, NULL, &p->instance);
    if (rc != VK_SUCCESS) return rc;
    count = 0;
    rc = vkEnumeratePhysicalDevices(p->instance, &count, NULL);
    if (rc != VK_SUCCESS || !count) return rc != VK_SUCCESS ? rc : VK_ERROR_INITIALIZATION_FAILED;
    VkPhysicalDevice *devices = calloc(count, sizeof(*devices));
    if (!devices) return VK_ERROR_OUT_OF_HOST_MEMORY;
    rc = vkEnumeratePhysicalDevices(p->instance, &count, devices);
    if (rc != VK_SUCCESS) { free(devices); return rc; }
    for (uint32_t d = 0; d < count && !p->physical; ++d) {
        uint32_t n = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(devices[d], &n, NULL);
        VkQueueFamilyProperties *q = calloc(n ? n : 1, sizeof(*q));
        if (!q) { free(devices); return VK_ERROR_OUT_OF_HOST_MEMORY; }
        vkGetPhysicalDeviceQueueFamilyProperties(devices[d], &n, q);
        for (uint32_t i = 0; i < n; ++i) {
            if (q[i].queueCount && (q[i].queueFlags & VK_QUEUE_COMPUTE_BIT)) {
                p->physical = devices[d]; p->family = i; break;
            }
        }
        free(q);
    }
    free(devices);
    if (!p->physical) return VK_ERROR_FEATURE_NOT_PRESENT;
    VkPhysicalDeviceProperties props;
    vkGetPhysicalDeviceProperties(p->physical, &props);
    fprintf(p->report, "{\"schema\":1,\"stage\":\"native_gpu\",\"device\":");
    json_string(p->report, props.deviceName);
    fprintf(p->report, ",\"api_version\":%u,\"driver_version\":%u,\"device_type\":%u,\"vendor_id\":%u,\"device_id\":%u}\n",
            props.apiVersion, props.driverVersion, (unsigned)props.deviceType, props.vendorID, props.deviceID);
    const int hardware = props.deviceType != VK_PHYSICAL_DEVICE_TYPE_CPU;
    result(p, "hardware_device", hardware, (long)props.deviceType);
    if (!hardware) return VK_ERROR_FEATURE_NOT_PRESENT;
    sample_capabilities(p, &props);
    if (props.apiVersion < VK_API_VERSION_1_1) return VK_ERROR_INCOMPATIBLE_DRIVER;

    count = 0;
    rc = vkEnumerateDeviceExtensionProperties(p->physical, NULL, &count, NULL);
    if (rc != VK_SUCCESS) return rc;
    exts = calloc(count ? count : 1, sizeof(*exts));
    if (!exts) return VK_ERROR_OUT_OF_HOST_MEMORY;
    rc = vkEnumerateDeviceExtensionProperties(p->physical, NULL, &count, exts);
    const char *required[] = {"VK_KHR_buffer_device_address", "VK_KHR_8bit_storage", "VK_KHR_shader_float_controls"};
    const char *enabled[4]; uint32_t enabled_count = 0;
    int missing = 0;
    for (uint32_t i = 0; i < 3; ++i) {
        int ok = extension(exts, count, required[i]);
        result(p, required[i], ok, 0); missing |= !ok;
        enabled[enabled_count++] = required[i];
    }
    if (extension(exts, count, "VK_KHR_portability_subset")) enabled[enabled_count++] = "VK_KHR_portability_subset";
    free(exts);
    if (rc != VK_SUCCESS) return rc;
    if (missing) return VK_ERROR_EXTENSION_NOT_PRESENT;
    VkPhysicalDevice8BitStorageFeatures bytes = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_8BIT_STORAGE_FEATURES};
    VkPhysicalDeviceBufferDeviceAddressFeatures bda = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_BUFFER_DEVICE_ADDRESS_FEATURES, .pNext = &bytes};
    VkPhysicalDeviceFeatures2 features = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, .pNext = &bda};
    vkGetPhysicalDeviceFeatures2(p->physical, &features);
    VkPhysicalDeviceFloatControlsProperties floats = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FLOAT_CONTROLS_PROPERTIES};
    VkPhysicalDeviceProperties2 props2 = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = &floats};
    vkGetPhysicalDeviceProperties2(p->physical, &props2);
#define REQUIRE_FEATURE(label, field) do { int ok = !!(field); result(p, label, ok, 0); missing |= !ok; } while (0)
    REQUIRE_FEATURE("bufferDeviceAddress", bda.bufferDeviceAddress);
    REQUIRE_FEATURE("storageBuffer8BitAccess", bytes.storageBuffer8BitAccess);
    REQUIRE_FEATURE("shaderInt64", features.features.shaderInt64);
    REQUIRE_FEATURE("textureCompressionBC", features.features.textureCompressionBC);
    REQUIRE_FEATURE("vertexPipelineStoresAndAtomics", features.features.vertexPipelineStoresAndAtomics);
    REQUIRE_FEATURE("fragmentStoresAndAtomics", features.features.fragmentStoresAndAtomics);
    REQUIRE_FEATURE("samplerAnisotropy", features.features.samplerAnisotropy);
    REQUIRE_FEATURE("shaderSignedZeroInfNanPreserveFloat32", floats.shaderSignedZeroInfNanPreserveFloat32);
#undef REQUIRE_FEATURE
    if (missing) return VK_ERROR_FEATURE_NOT_PRESENT;
    /* Enable only what these execution tests actually use. */
    memset(&features.features, 0, sizeof(features.features));
    features.features.shaderInt64 = VK_TRUE;
    features.features.textureCompressionBC = VK_TRUE;
    bytes.uniformAndStorageBuffer8BitAccess = VK_FALSE; bytes.storagePushConstant8 = VK_FALSE;
    bda.bufferDeviceAddressCaptureReplay = VK_FALSE; bda.bufferDeviceAddressMultiDevice = VK_FALSE;
    float priority = 1.0f;
    VkDeviceQueueCreateInfo queue = {.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
        .queueFamilyIndex = p->family, .queueCount = 1, .pQueuePriorities = &priority};
    VkDeviceCreateInfo create = {.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .pNext = &features,
        .queueCreateInfoCount = 1, .pQueueCreateInfos = &queue,
        .enabledExtensionCount = enabled_count, .ppEnabledExtensionNames = enabled};
    rc = vkCreateDevice(p->physical, &create, NULL, &p->device);
    if (rc != VK_SUCCESS) return rc;
    vkGetDeviceQueue(p->device, p->family, 0, &p->queue);
    VkCommandPoolCreateInfo pool = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
        .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT, .queueFamilyIndex = p->family};
    return vkCreateCommandPool(p->device, &pool, NULL, &p->pool);
}

static uint32_t memory_type(Probe *p, uint32_t bits, VkMemoryPropertyFlags flags) {
    VkPhysicalDeviceMemoryProperties props;
    vkGetPhysicalDeviceMemoryProperties(p->physical, &props);
    for (uint32_t i = 0; i < props.memoryTypeCount; ++i)
        if ((bits & (1u << i)) && (props.memoryTypes[i].propertyFlags & flags) == flags) return i;
    return UINT32_MAX;
}
static void free_buffer(Probe *p, Buffer *b) {
    if (b->mapped) vkUnmapMemory(p->device, b->memory);
    if (b->buffer) vkDestroyBuffer(p->device, b->buffer, NULL);
    if (b->memory) vkFreeMemory(p->device, b->memory, NULL);
    memset(b, 0, sizeof(*b));
}
static VkResult buffer(Probe *p, VkDeviceSize size, VkBufferUsageFlags usage, Buffer *b) {
    VkBufferCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
        .size = size, .usage = usage, .sharingMode = VK_SHARING_MODE_EXCLUSIVE};
    VkResult rc = vkCreateBuffer(p->device, &ci, NULL, &b->buffer);
    if (rc != VK_SUCCESS) return rc;
    VkMemoryRequirements req; vkGetBufferMemoryRequirements(p->device, b->buffer, &req);
    uint32_t type = memory_type(p, req.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT);
    if (type == UINT32_MAX) return VK_ERROR_FEATURE_NOT_PRESENT;
    VkMemoryAllocateFlagsInfo flags = {.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_FLAGS_INFO,
        .flags = VK_MEMORY_ALLOCATE_DEVICE_ADDRESS_BIT};
    VkMemoryAllocateInfo ai = {.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
        .allocationSize = req.size, .memoryTypeIndex = type,
        .pNext = (usage & VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT) ? &flags : NULL};
    rc = vkAllocateMemory(p->device, &ai, NULL, &b->memory);
    if (rc == VK_SUCCESS) rc = vkBindBufferMemory(p->device, b->buffer, b->memory, 0);
    if (rc == VK_SUCCESS) rc = vkMapMemory(p->device, b->memory, 0, VK_WHOLE_SIZE, 0, &b->mapped);
    return rc;
}
static VkResult sync_memory(Probe *p, Buffer *b, int invalidate) {
    VkMappedMemoryRange range = {.sType = VK_STRUCTURE_TYPE_MAPPED_MEMORY_RANGE,
        .memory = b->memory, .size = VK_WHOLE_SIZE};
    return invalidate ? vkInvalidateMappedMemoryRanges(p->device, 1, &range) : vkFlushMappedMemoryRanges(p->device, 1, &range);
}
static VkResult shader(Probe *p, const char *dir, const char *file, VkShaderModule *module) {
    char path[4096];
    if (snprintf(path, sizeof(path), "%s/%s", dir, file) >= (int)sizeof(path)) return VK_ERROR_INITIALIZATION_FAILED;
    FILE *in = fopen(path, "rb"); if (!in) return VK_ERROR_INITIALIZATION_FAILED;
    if (fseek(in, 0, SEEK_END)) { fclose(in); return VK_ERROR_INITIALIZATION_FAILED; }
    long size = ftell(in); rewind(in);
    if (size <= 0 || size % 4 || size > 1024 * 1024) { fclose(in); return VK_ERROR_INITIALIZATION_FAILED; }
    uint32_t *data = malloc((size_t)size);
    if (!data) { fclose(in); return VK_ERROR_OUT_OF_HOST_MEMORY; }
    size_t got = fread(data, 1, (size_t)size, in); fclose(in);
    VkResult rc = VK_ERROR_INITIALIZATION_FAILED;
    if (got == (size_t)size) {
        VkShaderModuleCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
            .codeSize = (size_t)size, .pCode = data};
        rc = vkCreateShaderModule(p->device, &ci, NULL, module);
    }
    free(data); return rc;
}
static VkResult pipeline(Probe *p, VkShaderModule module, VkPipelineLayout layout, VkPipeline *out) {
    VkComputePipelineCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
        .stage = {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
            .stage = VK_SHADER_STAGE_COMPUTE_BIT, .module = module, .pName = "main"}, .layout = layout};
    return vkCreateComputePipelines(p->device, VK_NULL_HANDLE, 1, &ci, NULL, out);
}
static VkResult begin(Probe *p, VkCommandBuffer *cmd) {
    VkCommandBufferAllocateInfo ai = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
        .commandPool = p->pool, .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
    VkResult rc = vkAllocateCommandBuffers(p->device, &ai, cmd);
    if (rc != VK_SUCCESS) return rc;
    VkCommandBufferBeginInfo bi = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
    return vkBeginCommandBuffer(*cmd, &bi);
}
static VkResult submit(Probe *p, VkCommandBuffer cmd) {
    VkMemoryBarrier barrier = {.sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .srcAccessMask = VK_ACCESS_SHADER_WRITE_BIT, .dstAccessMask = VK_ACCESS_HOST_READ_BIT};
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, VK_PIPELINE_STAGE_HOST_BIT,
        0, 1, &barrier, 0, NULL, 0, NULL);
    VkResult rc = vkEndCommandBuffer(cmd);
    VkFence fence = VK_NULL_HANDLE;
    VkFenceCreateInfo fi = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    if (rc == VK_SUCCESS) rc = vkCreateFence(p->device, &fi, NULL, &fence);
    VkSubmitInfo si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO, .commandBufferCount = 1, .pCommandBuffers = &cmd};
    if (rc == VK_SUCCESS) rc = vkQueueSubmit(p->queue, 1, &si, fence);
    if (rc == VK_SUCCESS) {
        rc = vkWaitForFences(p->device, 1, &fence, VK_TRUE, UINT64_C(10000000000));
        /* A failed wait does not prove the accepted submission finished.
         * Device loss permits cleanup; all other failures terminate this
         * isolated probe before potentially in-flight resources are freed. */
        if (rc != VK_SUCCESS && rc != VK_ERROR_DEVICE_LOST) {
            result(p, rc == VK_TIMEOUT ? "gpu_timeout" : "gpu_wait_failed", 0, rc);
            fflush(p->report);
            exit(2);
        }
    }
    if (fence) vkDestroyFence(p->device, fence, NULL);
    return rc;
}

static VkResult bda_test(Probe *p, const char *dir) {
    Buffer data = {0}; VkShaderModule module = VK_NULL_HANDLE;
    VkPipelineLayout layout = VK_NULL_HANDLE; VkPipeline compute = VK_NULL_HANDLE;
    VkCommandBuffer cmd = VK_NULL_HANDLE;
    VkResult rc = buffer(p, 80, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT | VK_BUFFER_USAGE_SHADER_DEVICE_ADDRESS_BIT, &data);
#define TRY(call) do { rc = (call); if (rc != VK_SUCCESS) { \
    fprintf(p->report, "{\"schema\":1,\"stage\":\"native_gpu\",\"operation_line\":%d,\"code\":%d}\n", __LINE__, (int)rc); \
    goto done; } } while (0)
    if (rc != VK_SUCCESS) goto done;
    memset(data.mapped, 0xa5, 80); TRY(sync_memory(p, &data, 0));
    TRY(shader(p, dir, "bda_bytes.spv", &module));
    VkPushConstantRange push = {.stageFlags = VK_SHADER_STAGE_COMPUTE_BIT, .size = 8};
    VkPipelineLayoutCreateInfo li = {.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .pushConstantRangeCount = 1, .pPushConstantRanges = &push};
    TRY(vkCreatePipelineLayout(p->device, &li, NULL, &layout));
    TRY(pipeline(p, module, layout, &compute));
    VkBufferDeviceAddressInfo address_info = {.sType = VK_STRUCTURE_TYPE_BUFFER_DEVICE_ADDRESS_INFO, .buffer = data.buffer};
    PFN_vkGetBufferDeviceAddressKHR get_address = (PFN_vkGetBufferDeviceAddressKHR)vkGetDeviceProcAddr(p->device, "vkGetBufferDeviceAddressKHR");
    if (!get_address) { rc = VK_ERROR_EXTENSION_NOT_PRESENT; goto done; }
    VkDeviceAddress address = get_address(p->device, &address_info);
    fprintf(p->report, "{\"schema\":1,\"stage\":\"native_gpu\",\"test\":\"bda_address\",\"address\":\"0x%llx\"}\n",
        (unsigned long long)address);
    if (!address) { rc = VK_ERROR_INITIALIZATION_FAILED; goto done; }
    TRY(begin(p, &cmd));
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, compute);
    vkCmdPushConstants(cmd, layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, 8, &address);
    vkCmdDispatch(cmd, 1, 1, 1);
    TRY(submit(p, cmd)); TRY(sync_memory(p, &data, 1));
    for (uint32_t i = 0; i < 80; ++i) {
        const uint64_t wide = ((uint64_t)(i + 1) << 32) | (uint64_t)(i * 37 + 11);
        const uint64_t mixed = wide * 3 + UINT64_C(0xfffffffd);
        uint8_t expected = i < 64 ? (uint8_t)((uint32_t)mixed ^ (uint32_t)(mixed >> 32)) : 0xa5;
        if (((uint8_t *)data.mapped)[i] != expected) {
            fprintf(p->report, "{\"schema\":1,\"stage\":\"native_gpu\",\"test\":\"bda_mismatch\",\"offset\":%u,\"actual\":%u,\"expected\":%u}\n",
                i, (unsigned)((uint8_t *)data.mapped)[i], (unsigned)expected);
            rc = VK_ERROR_UNKNOWN; break;
        }
    }
done:
    if (cmd) vkFreeCommandBuffers(p->device, p->pool, 1, &cmd);
    if (compute) vkDestroyPipeline(p->device, compute, NULL);
    if (layout) vkDestroyPipelineLayout(p->device, layout, NULL);
    if (module) vkDestroyShaderModule(p->device, module, NULL);
    free_buffer(p, &data); return rc;
}

static VkResult bc_test(Probe *p, const char *dir) {
    Buffer upload = {0}, output = {0}; VkImage image = VK_NULL_HANDLE;
    VkDeviceMemory image_memory = VK_NULL_HANDLE; VkImageView view = VK_NULL_HANDLE;
    VkSampler sampler = VK_NULL_HANDLE; VkDescriptorSetLayout set_layout = VK_NULL_HANDLE;
    VkDescriptorPool descriptors = VK_NULL_HANDLE; VkPipelineLayout layout = VK_NULL_HANDLE;
    VkShaderModule module = VK_NULL_HANDLE; VkPipeline compute = VK_NULL_HANDLE;
    VkCommandBuffer cmd = VK_NULL_HANDLE; VkResult rc = VK_SUCCESS;
    TRY(buffer(p, 8, VK_BUFFER_USAGE_TRANSFER_SRC_BIT, &upload));
    /* BC1 endpoint 0 = RGB565 red, endpoint 1 = black; all selectors = 0. */
    const uint8_t red_block[8] = {0x00, 0xf8, 0x00, 0x00, 0, 0, 0, 0};
    memcpy(upload.mapped, red_block, 8); TRY(sync_memory(p, &upload, 0));
    TRY(buffer(p, 16, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT, &output));
    memset(output.mapped, 0, 16); TRY(sync_memory(p, &output, 0));
    VkImageCreateInfo ii = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO,
        .imageType = VK_IMAGE_TYPE_2D, .format = VK_FORMAT_BC1_RGBA_UNORM_BLOCK,
        .extent = {4,4,1}, .mipLevels = 1, .arrayLayers = 1, .samples = VK_SAMPLE_COUNT_1_BIT,
        .tiling = VK_IMAGE_TILING_OPTIMAL, .usage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT,
        .sharingMode = VK_SHARING_MODE_EXCLUSIVE};
    TRY(vkCreateImage(p->device, &ii, NULL, &image));
    VkMemoryRequirements req; vkGetImageMemoryRequirements(p->device, image, &req);
    uint32_t type = memory_type(p, req.memoryTypeBits, 0);
    if (type == UINT32_MAX) { rc = VK_ERROR_FEATURE_NOT_PRESENT; goto done; }
    VkMemoryAllocateInfo ai = {.sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, .allocationSize = req.size, .memoryTypeIndex = type};
    TRY(vkAllocateMemory(p->device, &ai, NULL, &image_memory));
    TRY(vkBindImageMemory(p->device, image, image_memory, 0));
    VkImageViewCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
        .image = image, .viewType = VK_IMAGE_VIEW_TYPE_2D, .format = ii.format,
        .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT,0,1,0,1}};
    TRY(vkCreateImageView(p->device, &vi, NULL, &view));
    VkSamplerCreateInfo sci = {.sType = VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO,
        .magFilter = VK_FILTER_NEAREST, .minFilter = VK_FILTER_NEAREST,
        .mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST, .addressModeU = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE,
        .addressModeV = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE, .addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE};
    TRY(vkCreateSampler(p->device, &sci, NULL, &sampler));
    VkDescriptorSetLayoutBinding bindings[] = {
        {.binding = 0, .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, .descriptorCount = 1, .stageFlags = VK_SHADER_STAGE_COMPUTE_BIT},
        {.binding = 1, .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, .descriptorCount = 1, .stageFlags = VK_SHADER_STAGE_COMPUTE_BIT}};
    VkDescriptorSetLayoutCreateInfo dli = {.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
        .bindingCount = 2, .pBindings = bindings};
    TRY(vkCreateDescriptorSetLayout(p->device, &dli, NULL, &set_layout));
    VkDescriptorPoolSize sizes[] = {{VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,1},{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,1}};
    VkDescriptorPoolCreateInfo dpi = {.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
        .maxSets = 1, .poolSizeCount = 2, .pPoolSizes = sizes};
    TRY(vkCreateDescriptorPool(p->device, &dpi, NULL, &descriptors));
    VkDescriptorSetAllocateInfo dai = {.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
        .descriptorPool = descriptors, .descriptorSetCount = 1, .pSetLayouts = &set_layout};
    VkDescriptorSet set; TRY(vkAllocateDescriptorSets(p->device, &dai, &set));
    VkDescriptorImageInfo dii = {.sampler = sampler, .imageView = view, .imageLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
    VkDescriptorBufferInfo dbi = {.buffer = output.buffer, .range = 16};
    VkWriteDescriptorSet writes[] = {
        {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstSet = set, .dstBinding = 0,
         .descriptorCount = 1, .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, .pImageInfo = &dii},
        {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstSet = set, .dstBinding = 1,
         .descriptorCount = 1, .descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, .pBufferInfo = &dbi}};
    vkUpdateDescriptorSets(p->device, 2, writes, 0, NULL);
    VkPipelineLayoutCreateInfo li = {.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .setLayoutCount = 1, .pSetLayouts = &set_layout};
    TRY(vkCreatePipelineLayout(p->device, &li, NULL, &layout));
    TRY(shader(p, dir, "bc_sample.spv", &module)); TRY(pipeline(p, module, layout, &compute));
    TRY(begin(p, &cmd));
    VkImageMemoryBarrier transition = {.sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
        .dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT, .oldLayout = VK_IMAGE_LAYOUT_UNDEFINED,
        .newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .image = image,
        .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT,0,1,0,1}};
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
        0, 0, NULL, 0, NULL, 1, &transition);
    VkBufferImageCopy copy = {.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT,0,0,1}, .imageExtent = {4,4,1}};
    vkCmdCopyBufferToImage(cmd, upload.buffer, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);
    transition.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT; transition.dstAccessMask = VK_ACCESS_SHADER_READ_BIT;
    transition.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL; transition.newLayout = VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL;
    vkCmdPipelineBarrier(cmd, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,
        0, 0, NULL, 0, NULL, 1, &transition);
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, compute);
    vkCmdBindDescriptorSets(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, layout, 0, 1, &set, 0, NULL);
    vkCmdDispatch(cmd, 1, 1, 1); TRY(submit(p, cmd)); TRY(sync_memory(p, &output, 1));
    const float expected[] = {1,0,0,1};
    for (unsigned i = 0; i < 4; ++i) {
        float actual = ((float *)output.mapped)[i];
        if (!isfinite(actual) || fabsf(actual - expected[i]) > 0.001f) { rc = VK_ERROR_UNKNOWN; break; }
    }
done:
    if (cmd) vkFreeCommandBuffers(p->device, p->pool, 1, &cmd);
    if (compute) vkDestroyPipeline(p->device, compute, NULL);
    if (module) vkDestroyShaderModule(p->device, module, NULL);
    if (layout) vkDestroyPipelineLayout(p->device, layout, NULL);
    if (descriptors) vkDestroyDescriptorPool(p->device, descriptors, NULL);
    if (set_layout) vkDestroyDescriptorSetLayout(p->device, set_layout, NULL);
    if (sampler) vkDestroySampler(p->device, sampler, NULL);
    if (view) vkDestroyImageView(p->device, view, NULL);
    if (image) vkDestroyImage(p->device, image, NULL);
    if (image_memory) vkFreeMemory(p->device, image_memory, NULL);
    free_buffer(p, &upload); free_buffer(p, &output); return rc;
}
#undef TRY

int aps5_gpu_probe_run(const char *shader_dir, FILE *report) {
    Probe p = {.report = report ? report : stdout};
    VkResult rc = initialize(&p); int failed = rc != VK_SUCCESS;
    result(&p, "device_creation", !failed, rc);
    const int capabilities_only = shader_dir && !strcmp(shader_dir, "--capabilities");
    if (!failed && !capabilities_only) {
        rc = bda_test(&p, shader_dir); result(&p, "bda_8bit_readback", rc == VK_SUCCESS, rc); failed |= rc != VK_SUCCESS;
        rc = bc_test(&p, shader_dir); result(&p, "bc1_sample_readback", rc == VK_SUCCESS, rc); failed |= rc != VK_SUCCESS;
    }
    if (p.pool) vkDestroyCommandPool(p.device, p.pool, NULL);
    if (p.device) vkDestroyDevice(p.device, NULL);
    if (p.instance) vkDestroyInstance(p.instance, NULL);
    result(&p, capabilities_only ? "capability_query_complete" : "offscreen_complete", !failed, failed);
    return failed ? 1 : 0;
}

#ifdef APS5_GPU_PROBE_CLI
int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: %s SHADER_DIRECTORY\n", argv[0]); return 2; }
    return aps5_gpu_probe_run(argv[1], stdout);
}
#endif
