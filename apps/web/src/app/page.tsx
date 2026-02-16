export default function HomePage(): JSX.Element {
  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "center", padding: 24 }}>
      <section style={{ textAlign: "center" }}>
        <h1 style={{ fontSize: 40, marginBottom: 12 }}>oh-my-stock</h1>
        <p style={{ color: "#334155", marginBottom: 20 }}>
          KR/US 급등락 이벤트를 근거와 함께 빠르게 확인하세요.
        </p>
        <a href="/login" style={{ marginRight: 16 }}>
          로그인
        </a>
        <a href="/signup">회원가입</a>
      </section>
    </main>
  );
}
