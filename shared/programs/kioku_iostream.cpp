// std::cin, std::cout and std::cerr for C++ programs (kioku_prog.c): the
// run's streams inside the app, the real ones in a process. Sources use
// kioku_cin(), kioku_cout() and kioku_cerr() where they had std::cin,
// std::cout and std::cerr (patched in by build_programs.sh).
#include <cstdio>
#include <iostream>
#include <streambuf>
#include <unistd.h>

extern "C" {
FILE *kioku_stdin(void);
FILE *kioku_stdout(void);
FILE *kioku_stderr(void);
int kioku_in_app(void);
}

namespace {

// reads what's there (a line from an interactive add-on) instead of waiting
// for a full buffer; writes straight through to the FILE
class FileBuf : public std::streambuf {
  public:
    explicit FileBuf(FILE *file) : file_(file) {}

  protected:
    int_type underflow() override {
        fflush(kioku_stdout());
        ssize_t n = read(fileno(file_), buf_, sizeof(buf_));
        if (n <= 0) return traits_type::eof();
        setg(buf_, buf_, buf_ + n);
        return traits_type::to_int_type(buf_[0]);
    }
    int_type overflow(int_type c) override {
        if (traits_type::eq_int_type(c, traits_type::eof())) return traits_type::not_eof(c);
        return fputc(c, file_) == EOF ? traits_type::eof() : c;
    }
    std::streamsize xsputn(const char *s, std::streamsize n) override {
        return fwrite(s, 1, n, file_);
    }
    int sync() override { return fflush(file_) == 0 ? 0 : -1; }

  private:
    FILE *file_;
    char buf_[4096];
};

// one run per thread (kioku_run starts a thread for each)
struct Streams {
    FileBuf in{kioku_stdin()};
    FileBuf out{kioku_stdout()};
    FileBuf err{kioku_stderr()};
    std::istream is{&in};
    std::ostream os{&out};
    std::ostream es{&err};
};

Streams &streams() {
    thread_local Streams s;
    return s;
}

}  // namespace

std::istream &kioku_cin() { return kioku_in_app() ? streams().is : std::cin; }
std::ostream &kioku_cout() { return kioku_in_app() ? streams().os : std::cout; }
std::ostream &kioku_cerr() { return kioku_in_app() ? streams().es : std::cerr; }
