// Original teaching example, not an AMReX implementation or performance claim.
// C++17: concrete callable + runtime extent + move-only owner + const element view.
#include <cmath>
#include <cstddef>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <utility>
#include <vector>

namespace hpc_style {

template <class T>
class View {
public:
    View (T* data, std::size_t size) noexcept : m_data(data), m_size(size) {}
    template <class U, std::enable_if_t<std::is_convertible_v<U(*)[], T(*)[]>, int> = 0>
    View (View<U> other) noexcept : m_data(other.data()), m_size(other.size()) {}
    T* data () const noexcept { return m_data; }
    std::size_t size () const noexcept { return m_size; }
    // Precondition: i < size(), owner alive, no reallocation since obtaining view.
    T& operator[] (std::size_t i) const noexcept { return m_data[i]; }
private:
    T* m_data;
    std::size_t m_size;
};

template <class T>
class Buffer {
public:
    explicit Buffer (std::size_t size) : m_data(size) {}
    Buffer (Buffer const&) = delete;
    Buffer& operator= (Buffer const&) = delete;
    Buffer (Buffer&&) noexcept = default;
    Buffer& operator= (Buffer&&) noexcept = default;
    // Contract: discard borrowed views before moving or destroying either owner.
    View<T> view () noexcept { return {m_data.data(), m_data.size()}; }
    View<T const> view () const noexcept { return {m_data.data(), m_data.size()}; }
private:
    std::vector<T> m_data;
};

struct Serial {};
#ifdef _OPENMP
struct OpenMP {};
#endif

template <class F>
void for_each_index (Serial, std::ptrdiff_t size, F const& operation) {
    for (std::ptrdiff_t i = 0; i < size; ++i) {
        operation(static_cast<std::size_t>(i));
    }
}

#ifdef _OPENMP
template <class F>
void for_each_index (OpenMP, std::ptrdiff_t size, F const& operation) {
    // Parallel entry owns this region; callable must be thread-safe and nonthrowing.
#pragma omp parallel for schedule(static)
    for (std::ptrdiff_t i = 0; i < size; ++i) {
        operation(static_cast<std::size_t>(i));
    }
    // Synchronous API: the implicit barrier completes before return.
}
#endif

template <class Execution, class T>
void axpby (Execution execution, View<T> output, View<T const> input, T a, T b) {
    static_assert(std::is_floating_point_v<T>, "axpby requires floating-point elements");
    if (input.size() != output.size()) {
        throw std::invalid_argument("axpby extent mismatch");
    }
    if (output.size() > static_cast<std::size_t>(std::numeric_limits<std::ptrdiff_t>::max())) {
        throw std::length_error("axpby extent exceeds index range");
    }
    // Contract: disjoint ranges or identical element-for-element alias only.
    // Partial overlap requires a different algorithm; no restrict promise is made.
    for_each_index(execution, static_cast<std::ptrdiff_t>(output.size()),
        [=](std::size_t i) noexcept { output[i] = a * input[i] + b * output[i]; });
}

void require (bool condition) {
    if (!condition) { throw std::runtime_error("correctness check failed"); }
}

template <class Execution, class T>
void check (Execution execution) {
    for (std::size_t n : {std::size_t{0}, std::size_t{1}, std::size_t{17}, std::size_t{4099}}) {
        Buffer<T> input(n), output(n);
        auto x = input.view();
        auto y = output.view();
        std::vector<long double> expected(n);
        for (std::size_t i = 0; i < n; ++i) {
            x[i] = T(i % 23) / T(8);
            y[i] = -T(i % 11) / T(4);
            expected[i] = 2.0L * static_cast<long double>(x[i])
                        - 0.5L * static_cast<long double>(y[i]);
        }
        auto const& read_only_owner = input;
        axpby(execution, y, read_only_owner.view(), T(2), T(-0.5));
        for (std::size_t i = 0; i < n; ++i) {
            auto error = std::abs(static_cast<long double>(y[i]) - expected[i]);
            require(error <= 8 * std::numeric_limits<T>::epsilon()
                * (1 + std::abs(expected[i])));
        }
        // Exact alias is element-local and has no cross-iteration dependency.
        axpby(execution, y, View<T const>(y), T(1), T(0));
        for (std::size_t i = 0; i < n; ++i) {
            require(std::abs(static_cast<long double>(y[i]) - expected[i])
                <= 8 * std::numeric_limits<T>::epsilon() * (1 + std::abs(expected[i])));
        }
        Buffer<T> moved(std::move(input));
        require(moved.view().size() == n);
        // x is intentionally not reused after the move per the public contract.
    }
    Buffer<T> a(3), b(4);
    bool detected = false;
    try {
        axpby(execution, a.view(), View<T const>(b.view()), T(1), T(1));
    } catch (std::invalid_argument const&) { detected = true; }
    require(detected);
}

struct BaseElement { int value; };
struct DerivedElement : BaseElement { int extra; };
// Pointer covariance does not imply array-layout compatibility.
static_assert(!std::is_constructible_v<View<BaseElement>, View<DerivedElement>>);
static_assert(std::is_trivially_copyable_v<View<double>>);
static_assert(std::is_constructible_v<View<double const>, View<double>>);
static_assert(!std::is_constructible_v<View<double>, View<double const>>);
static_assert(!std::is_copy_constructible_v<Buffer<double>>);
static_assert(std::is_same_v<decltype(std::declval<View<double> const>()[0]), double&>);
static_assert(std::is_same_v<decltype(std::declval<View<double const>>()[0]), double const&>);

} // namespace hpc_style

int main () {
    using namespace hpc_style;
    check<Serial, float>(Serial{});
    check<Serial, double>(Serial{});
#ifdef _OPENMP
    check<OpenMP, float>(OpenMP{});
    check<OpenMP, double>(OpenMP{});
#endif
    std::cout << "owner/view correctness checks passed; no performance claim\n";
}
