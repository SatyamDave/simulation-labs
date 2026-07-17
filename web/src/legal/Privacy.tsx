// Privacy Policy — public route /legal/privacy. DRAFT (see banner).

import LegalLayout, { H2, P, UL, LI, B } from "./LegalLayout";

export default function Privacy() {
  return (
    <LegalLayout title="Privacy Policy" updated="July 2026">
      <P>
        This Privacy Policy explains what data Simulation Labs collects, how we
        use it, and the choices you have. It applies to our conversion-research
        platform (the "Service"). For business customers, this policy works
        alongside your subscription agreement and any data-processing terms.
      </P>

      <H2>1. Data we collect</H2>
      <H2>Account and billing data</H2>
      <UL>
        <LI>Account details you provide: name, work email, organization, password (stored only as a hash).</LI>
        <LI>
          Billing data handled by our payment processor (Stripe). We do not store
          full card numbers; we receive limited billing metadata such as a
          customer id, plan, and payment status.
        </LI>
      </UL>

      <H2>Data you provide to run simulations</H2>
      <UL>
        <LI>Target URLs, tasks, persona/segment selections, and run configuration.</LI>
        <LI>
          The authorization attestation you make for each run — including the
          account that made it, the timestamp, and the target domain — retained
          as an audit record.
        </LI>
      </UL>

      <H2>Artifacts we generate for you</H2>
      <UL>
        <LI>
          Screenshots and <B>video recordings (.webm)</B> of the automated agent
          sessions against the target site you provide.
        </LI>
        <LI>
          <B>Synthesized voice audio</B> and text summaries of "exit interviews,"
          generated from each agent's recorded action trace.
        </LI>
        <LI>Reports: survival curves, abandonment heatmaps, and derived metrics.</LI>
      </UL>
      <P>
        These artifacts describe the behavior of <B>synthetic</B> agents on a page
        you control. If a target page you choose to test displays personal data,
        that data may appear in the resulting screenshots or recordings. You are
        responsible for the pages you point the Service at and for the personal
        data they contain.
      </P>

      <H2>Usage and technical data</H2>
      <UL>
        <LI>Log data, device/browser metadata, and IP address for security and reliability.</LI>
        <LI>Product usage events to operate, debug, and improve the Service.</LI>
      </UL>

      <H2>2. How we use data</H2>
      <UL>
        <LI>To provide the Service and generate your reports and artifacts.</LI>
        <LI>To authenticate you, secure the Service, and prevent abuse.</LI>
        <LI>To process payments and manage subscriptions.</LI>
        <LI>To maintain the authorization audit trail for runs.</LI>
        <LI>To communicate with you about the Service.</LI>
        <LI>To comply with legal obligations.</LI>
      </UL>
      <P>
        We do not sell your personal data. We do not use your Customer Data to
        train models for other customers without your permission.
      </P>

      <H2>3. Subprocessors</H2>
      <P>
        We share data with vetted service providers who process it only to help
        us run the Service, under confidentiality and data-protection
        obligations. Generic categories:
      </P>
      <UL>
        <LI>
          <B>Cloud hosting and infrastructure</B> — compute, storage, and
          databases where the Service and your artifacts are hosted.
        </LI>
        <LI>
          <B>Payment processing</B> — subscription billing and payment handling.
        </LI>
        <LI>
          <B>Voice synthesis</B> — generating the voice audio for exit-interview
          summaries.
        </LI>
      </UL>
      <P>
        A current list of named subprocessors is available on request. [Publish a
        specific subprocessor list before launch.]
      </P>

      <H2>4. Retention</H2>
      <P>
        We keep account data for the life of your account and as needed for legal
        and accounting purposes. Run artifacts (screenshots, video, audio,
        reports) are retained per your plan and settings; you can delete runs and
        their artifacts, and we remove them from active systems within a
        commercially reasonable period, subject to backups and legal holds.
      </P>

      <H2>5. Security</H2>
      <P>
        We use administrative, technical, and organizational measures to protect
        data, including encryption in transit, access controls, and scoped API
        keys. No system is perfectly secure; we cannot guarantee absolute
        security.
      </P>

      <H2>6. Your rights</H2>
      <P>
        Depending on where you are, you may have rights to access, correct,
        export, or delete your personal data, or to object to or restrict certain
        processing. To exercise them, contact us at the address below. For
        Customer Data processed on behalf of a business customer, we act on that
        customer's instructions.
      </P>

      <H2>7. International transfers</H2>
      <P>
        We may process data in countries other than yours. Where required, we use
        appropriate safeguards for cross-border transfers. [Confirm transfer
        mechanisms before launch.]
      </P>

      <H2>8. Children</H2>
      <P>
        The Service is for businesses and is not directed to children. We do not
        knowingly collect personal data from children.
      </P>

      <H2>9. Changes</H2>
      <P>
        We may update this policy; material changes will be communicated with
        reasonable notice. The "last updated" date reflects the current version.
      </P>

      <H2>10. Contact</H2>
      <P>Privacy questions or requests: privacy@simulationlabs.example.</P>
    </LegalLayout>
  );
}
