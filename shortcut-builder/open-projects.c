#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <ctype.h>
#include <errno.h>

#define MAX_LINE 1024
#define MAX_PATH 4096
#define MAX_REPOS 256
#define SCAN_LINE 16384

typedef struct {
    int is_remote;
    char host[MAX_PATH];
    char path[MAX_PATH];
} Repo;

void trim(char *str) {
    char *end;
    while (*str == ' ' || *str == '\t' || *str == '\r' || *str == '\n') str++;
    end = str + strlen(str) - 1;
    while (end > str && (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')) end--;
    *(end + 1) = '\0';
}

int hex_val(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

void url_decode(const char *src, char *dst, size_t dstsz) {
    size_t j = 0;
    for (size_t i = 0; src[i] && j + 1 < dstsz; i++) {
        int hi, lo;
        if (src[i] == '%' && (hi = hex_val(src[i + 1])) >= 0 && (lo = hex_val(src[i + 2])) >= 0) {
            dst[j++] = (char)((hi << 4) | lo);
            i += 2;
        } else {
            dst[j++] = src[i];
        }
    }
    dst[j] = '\0';
}

int is_hex_string(const char *s) {
    size_t n = strlen(s);
    if (n < 2 || (n % 2) != 0) return 0;
    for (size_t i = 0; i < n; i++) {
        if (hex_val(s[i]) < 0) return 0;
    }
    return 1;
}

void hex_decode(const char *src, char *dst, size_t dstsz) {
    size_t j = 0;
    for (size_t i = 0; src[i] && src[i + 1] && j + 1 < dstsz; i += 2) {
        int hi = hex_val(src[i]);
        int lo = hex_val(src[i + 1]);
        if (hi < 0 || lo < 0) break;
        dst[j++] = (char)((hi << 4) | lo);
    }
    dst[j] = '\0';
}

void json_string(const char *json, const char *key, char *out, size_t outsz) {
    char pat[128];
    snprintf(pat, sizeof(pat), "\"%s\":\"", key);
    const char *p = strstr(json, pat);
    out[0] = '\0';
    if (!p) return;
    p += strlen(pat);
    size_t j = 0;
    while (*p && *p != '"' && j + 1 < outsz) {
        out[j++] = *p++;
    }
    out[j] = '\0';
}

void normalize_host(char *host, size_t hostsz, const char *path) {
    if (host[0] == '\0' || strchr(host, '@')) return;
    if (strncmp(path, "/home/", 6) != 0) return;

    const char *user = path + 6;
    const char *slash = strchr(user, '/');
    if (!slash || slash == user) return;

    char uname[128];
    size_t n = (size_t)(slash - user);
    if (n >= sizeof(uname)) n = sizeof(uname) - 1;
    memcpy(uname, user, n);
    uname[n] = '\0';

    char tmp[MAX_PATH];
    snprintf(tmp, sizeof(tmp), "%s@%s", uname, host);
    strncpy(host, tmp, hostsz - 1);
    host[hostsz - 1] = '\0';
}

int repo_exists(Repo *repos, int count, int is_remote, const char *host, const char *path) {
    for (int i = 0; i < count; i++) {
        if (repos[i].is_remote != is_remote) continue;
        if (strcmp(repos[i].path, path) != 0) continue;
        if (is_remote && strcmp(repos[i].host, host) != 0) continue;
        return 1;
    }
    return 0;
}

void add_repo(Repo *repos, int *count, int is_remote, const char *host, const char *path) {
    if (!path || path[0] == '\0' || *count >= MAX_REPOS) return;
    if (strcmp(path, "/") == 0) return;
    if (repo_exists(repos, *count, is_remote, host ? host : "", path)) return;

    Repo *r = &repos[*count];
    memset(r, 0, sizeof(*r));
    r->is_remote = is_remote;
    strncpy(r->path, path, MAX_PATH - 1);
    if (is_remote && host) strncpy(r->host, host, MAX_PATH - 1);
    (*count)++;
}

int is_git_repo(const char *path) {
    struct stat st;
    if (stat(path, &st) != 0 || !S_ISDIR(st.st_mode)) return 0;
    char gitdir[MAX_PATH];
    snprintf(gitdir, sizeof(gitdir), "%s/.git", path);
    return access(gitdir, F_OK) == 0;
}

void add_decoded_uri(Repo *repos, int *count, const char *uri) {
    const char *remote_mark = strstr(uri, "ssh-remote+");
    if (remote_mark) {
        const char *auth = remote_mark + strlen("ssh-remote+");
        const char *slash = strchr(auth, '/');
        if (!slash || slash == auth) return;

        char authority[MAX_PATH];
        char path[MAX_PATH];
        size_t alen = (size_t)(slash - auth);
        if (alen >= sizeof(authority)) alen = sizeof(authority) - 1;
        memcpy(authority, auth, alen);
        authority[alen] = '\0';
        strncpy(path, slash, MAX_PATH - 1);
        path[MAX_PATH - 1] = '\0';

        char host[MAX_PATH];
        host[0] = '\0';
        if (is_hex_string(authority)) {
            char json[MAX_PATH];
            char hostname[MAX_PATH];
            char user[256];
            hex_decode(authority, json, sizeof(json));
            json_string(json, "hostName", hostname, sizeof(hostname));
            json_string(json, "user", user, sizeof(user));
            if (hostname[0] == '\0') return;
            if (user[0] != '\0') snprintf(host, sizeof(host), "%s@%s", user, hostname);
            else snprintf(host, sizeof(host), "%s", hostname);
        } else {
            strncpy(host, authority, sizeof(host) - 1);
        }
        host[sizeof(host) - 1] = '\0';
        normalize_host(host, sizeof(host), path);
        add_repo(repos, count, 1, host, path);
        return;
    }

    if (strncmp(uri, "file://", 7) == 0) {
        const char *path = uri + 7;
        if (path[0] == '\0' || strcmp(path, "/") == 0) return;
        add_repo(repos, count, 0, "", path);
    }
}

void consider_uri_token(const char *raw, Repo *repos, int *count) {
    if (strncmp(raw, "file://", 7) != 0 && strncmp(raw, "vscode-remote://", 16) != 0) return;
    char decoded[MAX_PATH];
    url_decode(raw, decoded, sizeof(decoded));
    add_decoded_uri(repos, count, decoded);
}

void scan_storage(const char *filename, Repo *repos, int *count) {
    FILE *fp = fopen(filename, "r");
    if (!fp) return;

    char line[SCAN_LINE];
    while (fgets(line, sizeof(line), fp)) {
        const char *p = line;
        while ((p = strchr(p, '"')) != NULL) {
            char raw[MAX_PATH];
            size_t j = 0;
            p++;
            while (*p && *p != '"' && j + 1 < sizeof(raw)) {
                if (*p == '\\' && p[1]) p++;
                raw[j++] = *p++;
            }
            raw[j] = '\0';
            if (*p == '"') p++;
            consider_uri_token(raw, repos, count);
        }
    }
    fclose(fp);
}

void scan_projects_conf(const char *filename, Repo *repos, int *count) {
    FILE *fp = fopen(filename, "r");
    if (!fp) return;

    char line[MAX_LINE];
    int in_local = 0, in_server = 0;
    while (fgets(line, sizeof(line), fp)) {
        trim(line);
        if (line[0] == '\0' || line[0] == '#') continue;
        if (strcmp(line, "[local]") == 0) {
            in_local = 1;
            in_server = 0;
            continue;
        }
        if (strcmp(line, "[server]") == 0) {
            in_local = 0;
            in_server = 1;
            continue;
        }
        if (line[0] == '[') {
            in_local = 0;
            in_server = 0;
            continue;
        }
        if (in_local) {
            add_repo(repos, count, 0, "", line);
        } else if (in_server) {
            char host[MAX_PATH];
            char remote_path[MAX_PATH];
            const char *colon = strrchr(line, ':');
            const char *at = strchr(line, '@');
            if (!colon || !at || at > colon) continue;
            size_t hlen = (size_t)(colon - line);
            if (hlen >= sizeof(host)) hlen = sizeof(host) - 1;
            memcpy(host, line, hlen);
            host[hlen] = '\0';
            strncpy(remote_path, colon + 1, sizeof(remote_path) - 1);
            remote_path[sizeof(remote_path) - 1] = '\0';
            normalize_host(host, sizeof(host), remote_path);
            add_repo(repos, count, 1, host, remote_path);
        }
    }
    fclose(fp);
}

void sanitize(const char *src, char *dst, size_t dstsz) {
    size_t j = 0;
    for (size_t i = 0; src[i] && j + 1 < dstsz; i++) {
        unsigned char c = (unsigned char)src[i];
        if (isalnum(c) || c == '-' || c == '_' || c == '.') {
            dst[j++] = (char)tolower(c);
        } else if (j > 0 && dst[j - 1] != '-') {
            dst[j++] = '-';
        }
    }
    while (j > 0 && dst[j - 1] == '-') j--;
    dst[j] = '\0';
}

void script_basename(const Repo *r, char *name, size_t namesz) {
    if (r->is_remote) {
        const char *rel = r->path;
        if (strncmp(rel, "/home/ubuntu/", 13) == 0) rel += 13;
        else if (rel[0] == '/') rel++;
        char slug[512];
        sanitize(rel, slug, sizeof(slug));
        if (strcmp(r->host, "ubuntu@51.91.52.243") == 0) {
            snprintf(name, namesz, "server-%s.sh", slug);
        } else {
            char hslug[512];
            sanitize(r->host, hslug, sizeof(hslug));
            snprintf(name, namesz, "%s-%s.sh", hslug, slug);
        }
    } else {
        const char *rel = r->path;
        const char *prefix = "/home/cardinal/";
        if (strncmp(rel, prefix, strlen(prefix)) == 0) rel += strlen(prefix);
        else if (rel[0] == '/') rel++;
        char slug[512];
        sanitize(rel, slug, sizeof(slug));
        snprintf(name, namesz, "%s.sh", slug);
    }
}

int name_taken(char taken[][512], int n, const char *name) {
    for (int i = 0; i < n; i++) {
        if (strcmp(taken[i], name) == 0) return 1;
    }
    return 0;
}

void shell_quote(const char *src, char *dst, size_t dstsz) {
    size_t j = 0;
    if (j + 1 < dstsz) dst[j++] = '\'';
    for (size_t i = 0; src[i] && j + 1 < dstsz; i++) {
        if (src[i] == '\'') {
            if (j + 4 >= dstsz) break;
            dst[j++] = '\'';
            dst[j++] = '\\';
            dst[j++] = '\'';
            dst[j++] = '\'';
        } else {
            dst[j++] = src[i];
        }
    }
    if (j + 1 < dstsz) dst[j++] = '\'';
    dst[j] = '\0';
}

int write_script(const char *dir, const char *filename, const Repo *r) {
    char filepath[MAX_PATH];
    snprintf(filepath, sizeof(filepath), "%s/%s", dir, filename);

    FILE *fp = fopen(filepath, "w");
    if (!fp) {
        perror(filepath);
        return 0;
    }

    fputs("#!/bin/bash\n", fp);
    if (r->is_remote) {
        char qpath[MAX_PATH * 2];
        if (strpbrk(r->path, " \t\"'$&;|<>()\\")) {
            shell_quote(r->path, qpath, sizeof(qpath));
            fprintf(fp, "/opt/antigravity-ide/antigravity-ide --remote ssh-remote+%s %s &\n", r->host, qpath);
        } else {
            fprintf(fp, "/opt/antigravity-ide/antigravity-ide --remote ssh-remote+%s %s &\n", r->host, r->path);
        }
    } else {
        char qpath[MAX_PATH * 2];
        shell_quote(r->path, qpath, sizeof(qpath));
        fprintf(fp, "/opt/antigravity-ide/antigravity-ide %s &\n", qpath);
    }
    fputs("disown\n", fp);
    fclose(fp);

    if (chmod(filepath, 0755) != 0) perror(filepath);
    printf("Wrote %s\n", filepath);
    return 1;
}

int generate_shortcuts(const char *outdir) {
    const char *home = getenv("HOME");
    if (!home || home[0] == '\0') home = "/home/cardinal";

    char storage_paths[3][MAX_PATH];
    snprintf(storage_paths[0], MAX_PATH, "%s/.config/Cursor/User/globalStorage/storage.json", home);
    snprintf(storage_paths[1], MAX_PATH, "%s/.config/Antigravity IDE/User/globalStorage/storage.json", home);
    snprintf(storage_paths[2], MAX_PATH, "%s/.config/Antigravity/User/globalStorage/storage.json", home);

    char conf_path[MAX_PATH];
    snprintf(conf_path, sizeof(conf_path), "%s/sbuilder/projects.conf", outdir);

    char self_path[MAX_PATH];
    snprintf(self_path, sizeof(self_path), "%s", outdir);

    Repo repos[MAX_REPOS];
    int count = 0;
    for (int i = 0; i < 3; i++) scan_storage(storage_paths[i], repos, &count);
    scan_projects_conf(conf_path, repos, &count);

    char remote_dir[MAX_PATH];
    char local_dir[MAX_PATH];
    snprintf(remote_dir, sizeof(remote_dir), "%s/antigravity-ide", outdir);
    snprintf(local_dir, sizeof(local_dir), "%s/local", outdir);
    if (mkdir(remote_dir, 0755) != 0 && errno != EEXIST) perror(remote_dir);
    if (mkdir(local_dir, 0755) != 0 && errno != EEXIST) perror(local_dir);

    char taken[MAX_REPOS][512];
    int taken_count = 0;
    int written = 0;

    for (int i = 0; i < count; i++) {
        if (!repos[i].is_remote) {
            if *.conf
(!is_git_repo(repos[i].path)) continue;
            if (strcmp(repos[i].path, self_path) == 0) continue;
            if (strcmp(repos[i].path, "/home/cardinal/Desktop/Shortcuts") == 0) continue;
        }

        char base[512];
        script_basename(&repos[i], base, sizeof(base));
        if (base[0] == '\0' || strcmp(base, ".sh") == 0) continue;

        char unique[512];
        strncpy(unique, base, sizeof(unique) - 1);
        unique[sizeof(unique) - 1] = '\0';
        int n = 2;
        while (name_taken(taken, taken_count, unique)) {
            char stem[480];
            strncpy(stem, base, sizeof(stem) - 1);
            stem[sizeof(stem) - 1] = '\0';
            char *dot = strrchr(stem, '.');
            if (dot) *dot = '\0';
            snprintf(unique, sizeof(unique), "%s-%d.sh", stem, n++);
        }
        snprintf(taken[taken_count], sizeof(taken[taken_count]), "%s", unique);
        taken_count++;

        const char *dir = repos[i].is_remote ? remote_dir : local_dir;
        if (write_script(dir, unique, &repos[i])) written++;
    }

    printf("Wrote %d shortcut scripts from %d detected folders\n", written, count);
    return 0;
}

int main(int argc, char *argv[]) {
    if (argc > 2) {
        fprintf(stderr, "Usage: %s [output-dir]\n", argv[0]);
        fprintf(stderr, "Writes shortcut scripts for detected repos. Does not open them.\n");
        return 1;
    }

    const char *outdir = (argc == 2) ? argv[1] : ".";
    return generate_shortcuts(outdir);
}
