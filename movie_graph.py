import jsonimport osimport sysfrom dataclasses import dataclassfrom typing import Any, Dict, List, Optional, Tuple

from neo4j import GraphDatabasefrom neo4j.exceptions import AuthError, ServiceUnavailable, Neo4jError



NEO4J_URI = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "muhammed665")NEO4J_DB = os.getenv("NEO4J_DB", "neo4j")  # Neo4j Desktop genelde "neo4j"



APP_TITLE = "🎬 MovieGraphPy (Neo4j) - Proje 3"

def hr() -> None:print("\n" + "=" * 62)

def header(title: str) -> None:hr()print(title)hr()

def info(msg: str) -> None:print(f"ℹ️  {msg}")

def ok(msg: str) -> None:print(f"✅ {msg}")

def warn(msg: str) -> None:print(f"⚠️  {msg}")

def err(msg: str) -> None:print(f"❌ {msg}")

def ask(prompt: str) -> str:return input(prompt).strip()

def ask_int(prompt: str) -> Optional[int]:s = input(prompt).strip()try:return int(s)except ValueError:return None



@dataclassclass MovieItem:title: strreleased: Optional[int] = None



class Neo4jDB:def init(self, uri: str, user: str, password: str, db_name: str) -> None:self.uri = uriself.user = userself.password = passwordself.db_name = db_nameself.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

def close(self) -> None:
    try:
        self.driver.close()
    except Exception:
        pass

def _session(self):
    return self.driver.session(database=self.db_name)

def test_connection(self) -> Tuple[bool, str]:
    """
    Bağlantı + veri var mı kontrolü.
    """
    try:
        with self._session() as s:
            s.run("RETURN 1").single()
            cnt = s.run("MATCH (m:Movie) RETURN count(m) AS c").single()["c"]
            if cnt == 0:
                return False, (
                    "Bağlantı başarılı ama Movie verisi yok (count=0). "
                    "Neo4j Desktop'ta ':play movies' ile dataset'i yükle. "
                    "Clean up çalıştırdıysan tekrar yükle."
                )
            return True, f"Bağlantı başarılı. Movie sayısı: {cnt}"
    except AuthError:
        return False, "AuthError: Kullanıcı adı/şifre hatalı."
    except ServiceUnavailable:
        return False, "ServiceUnavailable: Neo4j çalışmıyor veya Bolt (7687) kapalı."
    except Neo4jError as e:
        return False, f"Neo4jError: {e}"
    except Exception as e:
        return False, f"Bilinmeyen hata: {e}"


def search_movies(self, keyword: str, limit: int = 20) -> List[MovieItem]:
    q = """
    MATCH (m:Movie)
    WHERE toLower(m.title) CONTAINS toLower($kw)
    RETURN m.title AS title, m.released AS released
    ORDER BY m.released DESC
    LIMIT $limit
    """
    items: List[MovieItem] = []
    with self._session() as s:
        for r in s.run(q, kw=keyword, limit=limit):
            released = r.get("released")
            released_int = int(released) if released is not None else None
            items.append(MovieItem(title=r["title"], released=released_int))
    return items


def movie_details(self, title: str) -> Dict[str, Any]:
    q = """
    MATCH (m:Movie {title:$title})
    OPTIONAL MATCH (a:Person)-[r:ACTED_IN]->(m)
    OPTIONAL MATCH (d:Person)-[:DIRECTED]->(m)
    OPTIONAL MATCH (w:Person)-[:WROTE]->(m)
    OPTIONAL MATCH (p:Person)-[:PRODUCED]->(m)
    RETURN
      m.title AS title,
      m.released AS released,
      m.tagline AS tagline,
      m.rating AS rating,
      m.summary AS summary,
      collect(DISTINCT {name:a.name, roles:r.roles}) AS actors,
      collect(DISTINCT d.name) AS directors,
      collect(DISTINCT w.name) AS writers,
      collect(DISTINCT p.name) AS producers
    """
    with self._session() as s:
        rec = s.run(q, title=title).single()

    if not rec:
        return {"found": False}

    def clean_list(lst: Any) -> List[Any]:
        if not lst:
            return []
        return [x for x in lst if x]

    actors = [x for x in (rec.get("actors") or []) if x.get("name")]
    directors = clean_list(rec.get("directors"))
    writers = clean_list(rec.get("writers"))
    producers = clean_list(rec.get("producers"))

    released = rec.get("released")
    released_int = int(released) if released is not None else None

    return {
        "found": True,
        "title": rec.get("title"),
        "released": released_int,
        "tagline": rec.get("tagline"),
        "rating": rec.get("rating"),
        "summary": rec.get("summary"),
        "actors": actors,
        "directors": directors,
        "writers": writers,
        "producers": producers,
    }


def export_movie_subgraph(self, title: str, out_path: str) -> Tuple[bool, str]:
    """
    Seçili film + filmle ilişkili kişiler (ACTED_IN, DIRECTED, WROTE, PRODUCED)
    JSON formatında dışa aktarır.
    """
    q = """
    MATCH (m:Movie {title:$title})
    OPTIONAL MATCH (p:Person)-[rel]->(m)
    WHERE type(rel) IN ["ACTED_IN","DIRECTED","WROTE","PRODUCED","REVIEWED"]
    RETURN m, p, rel
    """
    with self._session() as s:
        rows = list(s.run(q, title=title))

    if not rows:
        return False, "Film bulunamadı veya film için ilişki yok."

    nodes: Dict[str, Dict[str, Any]] = {}
    rels: List[Dict[str, Any]] = []

    def node_id(n) -> str:
        label = list(n.labels)[0]
        key = n.get("title") or n.get("name") or str(n.element_id)
        return f"{label}:{key}"

    for row in rows:
        m = row.get("m")
        p = row.get("p")
        rel = row.get("rel")

        if m:
            mid = node_id(m)
            nodes[mid] = {"id": mid, "labels": list(m.labels), "properties": dict(m)}
        if p:
            pid = node_id(p)
            nodes[pid] = {"id": pid, "labels": list(p.labels), "properties": dict(p)}
        if rel and m and p:
            rels.append({
                "type": rel.type,
                "from": node_id(p),
                "to": node_id(m),
                "properties": dict(rel),
            })

    payload = {
        "meta": {
            "project": "Proje 3",
            "dataset": "Neo4j Movie Graph",
            "movie": title,
        },
        "nodes": list(nodes.values()),
        "relationships": rels,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return True, f"graph.json oluşturuldu: {out_path}"



class MovieGraphCLI:def init(self, db: Neo4jDB) -> None:self.db = dbself.last_results: List[MovieItem] = []self.selected_movie: Optional[MovieItem] = None

def show_menu(self) -> None:
    header(APP_TITLE)
    print(f"Bağlantı: {NEO4J_URI} | DB: {NEO4J_DB} | User: {NEO4J_USER}")
    print(f"Seçili Film: {self.selected_movie.title if self.selected_movie else '—'}")
    print("\n1) Film Ara")
    print("2) Film Detayı Göster")
    print("3) Seçili Film için graph.json Üret")
    print("4) Çıkış")

def run(self) -> None:
    # 1) Bağlantı kontrol
    ok_conn, msg = self.db.test_connection()
    header(APP_TITLE)
    if not ok_conn:
        err(msg)
        info("Çıkış yapılıyor.")
        return
    ok(msg)

    # 2) Menü döngüsü
    while True:
        self.show_menu()
        choice = ask("Seçim (1-4): ")

        if choice == "1":
            self.action_search()
        elif choice == "2":
            self.action_details()
        elif choice == "3":
            self.action_export()
        elif choice == "4":
            header("Çıkış")
            ok("Program kapatıldı.")
            break
        else:
            warn("Geçersiz seçim. 1-4 arası gir.")

def action_search(self) -> None:
    header("🔎 Film Arama")
    kw = ask("Arama kelimesi (örn: Matrix): ")
    if not kw:
        warn("Boş değer olmaz.")
        return

    try:
        self.last_results = self.db.search_movies(kw, limit=20)
    except Exception as e:
        err(f"Arama hatası: {e}")
        return

    if not self.last_results:
        warn("Sonuç bulunamadı.")
        self.selected_movie = None
        return

    print("\n--- Sonuçlar ---")
    for i, m in enumerate(self.last_results, 1):
        year = m.released if m.released is not None else "?"
        print(f"{i:02d}. {m.title} ({year})")

    idx = ask_int("\nFilm seç (numara): ")
    if idx is None:
        warn("Sayı girmelisin.")
        return
    if not (1 <= idx <= len(self.last_results)):
        warn("Numara aralık dışında.")
        return

    self.selected_movie = self.last_results[idx - 1]
    ok(f"Seçildi: {self.selected_movie.title}")


def action_details(self) -> None:
    header("🎞️ Film Detayı")
    if not self.selected_movie:
        warn("Önce film ara ve seç.")
        return

    title = self.selected_movie.title
    try:
        d = self.db.movie_details(title)
    except ServiceUnavailable:
        err("Neo4j bağlantısı yok (ServiceUnavailable). Neo4j çalışıyor mu?")
        return
    except AuthError:
        err("Yetkilendirme hatası (AuthError). Şifre doğru mu?")
        return
    except Neo4jError as e:
        err(f"Neo4j hatası: {e}")
        return
    except Exception as e:
        err(f"Bilinmeyen hata: {e}")
        return

    if not d.get("found"):
        err("Film bulunamadı. (Veri seti silinmiş olabilir.)")
        return

    print(f"Başlık  : {d.get('title')}")
    print(f"Yıl     : {d.get('released')}")
    print(f"Rating  : {d.get('rating')}")
    print(f"Tagline : {d.get('tagline')}")
    print(f"Summary : {d.get('summary')}")

    directors = d.get("directors", [])
    writers = d.get("writers", [])
    producers = d.get("producers", [])
    actors = d.get("actors", [])

    if directors:
        print(f"\nDirector : {', '.join(directors)}")
    if writers:
        print(f"Writers  : {', '.join(writers)}")
    if producers:
        print(f"Producers: {', '.join(producers)}")

    if actors:
        print("\nOyuncular (ilk 15):")
        for a in actors[:15]:
            roles = a.get("roles") or []
            roles_txt = f" | Roles: {roles}" if roles else ""
            print(f" - {a.get('name')}{roles_txt}")

    ok("Detay gösterimi tamamlandı.")


def action_export(self) -> None:
    header("📦 graph.json Üretimi")
    if not self.selected_movie:
        warn("Önce film ara ve seç.")
        return

    default_name = "graph.json"
    out_name = ask(f"Dosya adı (varsayılan: {default_name}): ") or default_name

    try:
        success, msg = self.db.export_movie_subgraph(self.selected_movie.title, out_name)
    except ServiceUnavailable:
        err("Neo4j bağlantısı yok (ServiceUnavailable). Neo4j çalışıyor mu?")
        return
    except AuthError:
        err("Yetkilendirme hatası (AuthError). Şifre doğru mu?")
        return
    except Neo4jError as e:
        err(f"Neo4j hatası: {e}")
        return
    except Exception as e:
        err(f"Bilinmeyen hata: {e}")
        return

    if success:
        ok(msg)
    else:
        err(msg)



def main() -> None:try:db = Neo4jDB(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DB)app = MovieGraphCLI(db)app.run()finally:try:db.close()except Exception:pass

if name == "main":# Python sürümü uyarısı (isteğe bağlı)if sys.version_info < (3, 9):warn("Öneri: Python 3.9+ kullan.")main()
