#include "engine/platform/profiling_csv.h"
#include <cassert>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <sys/wait.h>
#include <unistd.h>

int main() {
    char directory[] = "/tmp/pt-profile-recovery-XXXXXX";
    assert(mkdtemp(directory));
    const auto file = std::filesystem::path(directory) / "ticks.csv";
    const pid_t child = fork();
    assert(child >= 0);
    if (child == 0) {
        pt::ProfilingCsv csv(file.c_str(), "sample,value\n");
        for (int i = 0; i < 65; ++i) csv.Write("%d,%d\n", i, i * 2);
        std::_Exit(0); // Deliberately bypass destructors and atexit handlers.
    }
    int status = 0;
    assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    std::ifstream stream(file);
    std::string line;
    assert(std::getline(stream, line) && line == "sample,value");
    for (int i = 0; i < 60; ++i) {
        assert(std::getline(stream, line) && line == std::to_string(i) + "," + std::to_string(i * 2));
    }
    assert(!std::getline(stream, line)); // Unflushed tail must never be claimed.
    std::filesystem::remove_all(directory);
}
