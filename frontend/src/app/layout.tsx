import type { Metadata } from 'next';
import '../styles/globals.css';
import Shell from '../components/layout/Shell';
import { I18nProvider } from '../lib/i18n';
import { ThemeProvider } from '../providers/ThemeProvider';
import { ToastProvider } from '../components/ui/toast';

export const metadata: Metadata = {
  title: 'NOOSFORGE Security Intelligence — Continuous Security Platform',
  description: 'Enterprise self-hosted continuous security assessment, asset discovery, and vulnerability management platform.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className="dark" data-theme="obsidian-dark">
      <body className="bg-nf-950 text-nf-100 antialiased selection:bg-white/20 selection:text-white">
        <ThemeProvider>
          <I18nProvider>
            <ToastProvider>
              <Shell>{children}</Shell>
            </ToastProvider>
          </I18nProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
