import "./globals.css";

export const metadata = {
  title: "Warden — Permission Ledger",
  description: "Audit trail and approval ledger for the Warden triage agent",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
