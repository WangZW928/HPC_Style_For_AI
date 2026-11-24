// Original contract probes for Kokkos 5.3; not copied from upstream tests.
// Host-only checks deliberately do not claim device visibility or overlap coverage.
#include <Kokkos_Core.hpp>
#if !defined(KOKKOS_ENABLE_SERIAL) && !defined(KOKKOS_ENABLE_OPENMP)
#error "These host-only probes require Kokkos Serial or OpenMP."
#endif
#include <stdexcept>
#include <string>
#include <iostream>
#include <cstdlib>
#include <type_traits>

void check(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}

template <class Exec>
void check_contracts() {
    static_assert(Kokkos::SpaceAccessibility<Exec, Kokkos::HostSpace>::accessible);
    constexpr int rows = 7, cols = 11;
    Exec exec;
#ifdef KOKKOS_ENABLE_OPENMP
    if constexpr (std::is_same_v<Exec, Kokkos::OpenMP>) {
        if (const char* expected = std::getenv("HPC_STYLE_EXPECT_THREADS"))
            check(exec.concurrency() == std::stoi(expected), "OpenMP thread count differs from test configuration");
    }
#endif
    using left_view = Kokkos::View<long long**, Kokkos::LayoutLeft, Kokkos::HostSpace>;
    using right_view = Kokkos::View<long long**, Kokkos::LayoutRight, Kokkos::HostSpace>;
    left_view left(Kokkos::view_alloc(exec, "left"), rows, cols);
    right_view right(Kokkos::view_alloc(exec, "right"), rows, cols);
    Kokkos::parallel_for("fill logical indices",
        Kokkos::MDRangePolicy<Exec, Kokkos::Rank<2>>(exec, {0, 0}, {rows, cols}),
        KOKKOS_LAMBDA(int i, int j) { left(i, j) = 100 * i + j; });
    Kokkos::deep_copy(exec, right, left);
    exec.fence("host observes layout conversion");
    for (int i = 0; i < rows; ++i)
        for (int j = 0; j < cols; ++j)
            check(right(i, j) == 100 * i + j, "layout conversion changed logical values");

    auto alias = left;
    auto maybe_alias = Kokkos::create_mirror_view(left);
    auto snapshot = Kokkos::create_mirror(left);
    check(alias.data() == left.data(), "View copy should share allocation");
    check(maybe_alias.data() == left.data(), "HostSpace mirror_view should alias");
    check(snapshot.data() != left.data(), "create_mirror should allocate independently");
    Kokkos::deep_copy(exec, snapshot, left);
    exec.fence("snapshot ready before host mutation");
    left(0, 0) = -1;
    check(alias(0, 0) == -1 && maybe_alias(0, 0) == -1, "shared allocation lost aliasing");
    check(snapshot(0, 0) == 0, "independent snapshot changed with source");

    // A row in LayoutLeft is strided: copying elements is not a raw byte copy.
    auto row = Kokkos::subview(left, 3, Kokkos::ALL());
    Kokkos::View<long long*, Kokkos::HostSpace> gathered("gathered", cols);
    check(row.stride(0) > 1, "probe requires a non-unit stride");
    Kokkos::deep_copy(exec, gathered, row);
    exec.fence("strided copy visible to host");
    for (int j = 0; j < cols; ++j)
        check(gathered(j) == 300 + j, "strided logical copy failed");

    long long scalar_sum = -1;
    Kokkos::parallel_reduce("sum into host scalar",
        Kokkos::RangePolicy<Exec>(exec, 0, rows * cols),
        KOKKOS_LAMBDA(int k, long long& acc) { acc += k; }, scalar_sum);
    check(scalar_sum == (rows * cols - 1LL) * rows * cols / 2,
          "host scalar reduction result not ready or incorrect");
    long long empty_sum = -1;
    Kokkos::parallel_reduce("empty sum", Kokkos::RangePolicy<Exec>(exec, 0, 0),
        KOKKOS_LAMBDA(int k, long long& acc) { acc += k; }, empty_sum);
    check(empty_sum == 0, "empty reduction identity incorrect");

    Kokkos::View<long long, Kokkos::HostSpace> view_sum("view result");
    Kokkos::parallel_reduce("sum into view", Kokkos::RangePolicy<Exec>(exec, 0, rows * cols),
        KOKKOS_LAMBDA(int k, long long& acc) { acc += k; }, view_sum);
    exec.fence("view result ready for host consumption");
    check(view_sum() == scalar_sum, "View reduction differs from scalar reference");

    Kokkos::View<long long*, Kokkos::HostSpace> prefix("prefix", rows * cols);
    Kokkos::View<int*, Kokkos::HostSpace> final_writes("final writes", rows * cols);
    Kokkos::parallel_scan("exclusive prefix with final-only side effects",
        Kokkos::RangePolicy<Exec>(exec, 0, rows * cols),
        KOKKOS_LAMBDA(int k, long long& update, bool final_pass) {
            if (final_pass) {
                prefix(k) = update;
                Kokkos::atomic_fetch_add(&final_writes(k), 1);
            }
            update += k;
        });
    exec.fence("scan output ready");
    for (int k = 0; k < rows * cols; ++k) {
        check(prefix(k) == k * (k - 1LL) / 2, "scan differs from exact prefix reference");
        check(final_writes(k) == 1, "scan final output must be written once");
    }

    using policy = Kokkos::TeamPolicy<Exec>;
    using member = typename policy::member_type;
    using scratch_view = Kokkos::View<long long*, typename member::scratch_memory_space,
                                      Kokkos::MemoryTraits<Kokkos::Unmanaged>>;
    Kokkos::View<long long*, Kokkos::HostSpace> team_sums("team sums", rows);
    Kokkos::View<int*, Kokkos::HostSpace> actual_team_sizes("actual team sizes", rows);
    Kokkos::View<int*, Kokkos::HostSpace> single_writes("single writes", rows);
    // AUTO in this pinned OpenMP implementation defaults to a one-member team.
    // Ask for two members when available, so the shared-data contract is exercised.
    const int requested_team_size = exec.concurrency() >= 2 ? 2 : 1;
    auto teams = policy(exec, rows, requested_team_size);
    teams.set_scratch_size(0, Kokkos::PerTeam(scratch_view::shmem_size(cols)));
    Kokkos::parallel_for("team scratch producer consumer", teams,
        KOKKOS_LAMBDA(const member& team) {
            scratch_view temporary(team.team_scratch(0), cols);
            const int i = team.league_rank();
            Kokkos::parallel_for(Kokkos::TeamThreadRange(team, cols),
                [=](int j) { temporary(j) = 100 * i + j; });
            team.team_barrier();
            long long local_sum = 0;
            Kokkos::parallel_reduce(Kokkos::TeamThreadRange(team, cols),
                [=](int j, long long& acc) { acc += temporary(j); }, local_sum);
            Kokkos::single(Kokkos::PerTeam(team), [=]() {
                team_sums(i) = local_sum;
                actual_team_sizes(i) = team.team_size();
                Kokkos::atomic_fetch_add(&single_writes(i), 1);
            });
        });
    exec.fence("team results ready");
    for (int i = 0; i < rows; ++i) {
        check(team_sums(i) == 100LL * i * cols + cols * (cols - 1LL) / 2,
              "team scratch or collective ownership incorrect");
        check(actual_team_sizes(i) == requested_team_size, "effective team size differs from requested probe coverage");
        check(single_writes(i) == 1, "PerTeam result side effect must occur once");
    }
    std::cout << Exec::name() << ": concurrency=" << exec.concurrency()
              << ", team_size=" << requested_team_size
              << "; layout, alias, mirror, stride, reduction, scan, team checks passed\n";
}

int main(int argc, char** argv) {
    Kokkos::ScopeGuard guard(argc, argv);
    try {
#ifdef KOKKOS_ENABLE_SERIAL
        check_contracts<Kokkos::Serial>();
#endif
#ifdef KOKKOS_ENABLE_OPENMP
        check_contracts<Kokkos::OpenMP>();
#endif
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
