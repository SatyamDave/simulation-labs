// Terms of Service — public route /legal/terms. DRAFT (see banner).

import LegalLayout, { H2, P, UL, LI, B } from "./LegalLayout";

export default function Terms() {
  return (
    <LegalLayout title="Terms of Service" updated="July 2026">
      <P>
        These Terms of Service (the "Terms") govern your access to and use of the
        Simulation Labs conversion-research platform, including the website,
        dashboard, command-line tools, and APIs (together, the "Service").
        Simulation Labs ("we", "us") provides the Service; by creating an
        account, running a simulation, or otherwise using the Service, you and
        the organization you represent ("you", "Customer") agree to these Terms.
      </P>

      <H2>1. The Service</H2>
      <P>
        Simulation Labs helps teams find where real users abandon a flow. We
        point a swarm of synthetic users — automated browser agents with
        mechanically varied perception and interaction — at a website you
        provide, give them a task (for example, sign up or check out), and report
        where and why they drop off, including survival curves, abandonment
        heatmaps, video recordings, and voice exit-interview summaries grounded
        in each agent's action trace. The Service is a conversion-rate
        optimization (CRO) research tool. It is not a substitute for your own
        testing, monitoring, or professional advice.
      </P>

      <H2>2. Accounts</H2>
      <UL>
        <LI>You must provide accurate account information and keep it current.</LI>
        <LI>
          You are responsible for all activity under your account and for keeping
          your credentials and API keys confidential. Notify us promptly of any
          unauthorized use.
        </LI>
        <LI>
          You must be at least 18 and have authority to bind your organization to
          these Terms.
        </LI>
      </UL>

      <H2>3. Your responsibilities for target sites</H2>
      <P>
        <B>
          You may only run simulations against a website that you own or that you
          have explicit permission to test.
        </B>{" "}
        Running automated agents against a site you do not control may violate
        that site's terms, computer-misuse laws, or the rights of others. When
        you start a run you attest, for that specific target, that you have the
        required authorization. You are solely responsible for that attestation
        and for the consequences of any run you start. We may record, audit, and
        act on these attestations, and may suspend runs or accounts we believe
        are used without authorization. See the{" "}
        <B>Acceptable Use Policy</B> for details.
      </P>

      <H2>4. Customer data and content</H2>
      <P>
        "Customer Data" means the URLs, tasks, configurations, and the artifacts
        the Service generates for you — including screenshots, video recordings
        (.webm), and synthesized voice audio of simulated sessions. You retain
        all rights to your Customer Data. You grant us a limited license to
        process it solely to provide, secure, and improve the Service for you and
        to comply with law. Our handling of Customer Data is described in the{" "}
        <B>Privacy Policy</B>.
      </P>

      <H2>5. Fees and billing</H2>
      <UL>
        <LI>
          Paid plans are billed in advance through our payment processor
          (Stripe). By subscribing you authorize recurring charges for the plan
          and usage you select.
        </LI>
        <LI>
          Fees are exclusive of taxes, which you are responsible for except for
          taxes on our net income.
        </LI>
        <LI>
          Cancellation and refund terms are set out in the{" "}
          <B>Acceptable Use &amp; Refund Policy</B>.
        </LI>
      </UL>

      <H2>6. Acceptable use</H2>
      <P>
        Your use of the Service is subject to the Acceptable Use Policy, which is
        incorporated into these Terms. Violating it is a breach of these Terms.
      </P>

      <H2>7. Intellectual property</H2>
      <P>
        We and our licensors own the Service and all related software, models,
        and documentation. These Terms grant you a limited, non-exclusive,
        non-transferable right to use the Service during your subscription. You
        may not copy, resell, reverse engineer, or use the Service to build a
        competing product.
      </P>

      <H2>8. Third-party services</H2>
      <P>
        The Service relies on subprocessors, including cloud infrastructure
        providers, a payment processor, and voice-synthesis providers. Their
        processing is covered by our Privacy Policy. We are not responsible for
        third-party websites you choose to target.
      </P>

      <H2>9. Disclaimers</H2>
      <P>
        The Service is provided "as is" and "as available." Simulation runs are
        probabilistic research signals, not guarantees; we do not warrant any
        particular result, completion rate, or business outcome. To the fullest
        extent permitted by law, we disclaim all implied warranties, including
        merchantability, fitness for a particular purpose, and non-infringement.
      </P>

      <H2>10. Limitation of liability</H2>
      <P>
        To the fullest extent permitted by law, neither party is liable for
        indirect, incidental, special, consequential, or punitive damages, or for
        lost profits or data. Our total liability arising out of or relating to
        the Service will not exceed the fees you paid us in the 12 months before
        the event giving rise to the claim. Nothing limits liability that cannot
        be limited by law.
      </P>

      <H2>11. Indemnification</H2>
      <P>
        You will defend and indemnify us against third-party claims arising from
        your Customer Data, your use of the Service, or your breach of these
        Terms — including any claim that a target site was tested without proper
        authorization.
      </P>

      <H2>12. Suspension and termination</H2>
      <P>
        You may cancel at any time as described in the Refund Policy. We may
        suspend or terminate access for breach of these Terms, non-payment, or
        use that we reasonably believe is unauthorized, unlawful, or harmful.
        Sections that by their nature should survive termination will survive.
      </P>

      <H2>13. Changes to these Terms</H2>
      <P>
        We may update these Terms from time to time. If a change is material we
        will provide reasonable notice. Continued use after the effective date
        means you accept the updated Terms.
      </P>

      <H2>14. Governing law</H2>
      <P>
        These Terms are governed by the laws of the jurisdiction in which
        Simulation Labs is established, excluding its conflict-of-laws rules.
        [Insert governing law, venue, and dispute-resolution mechanism before
        launch.]
      </P>

      <H2>15. Contact</H2>
      <P>Questions about these Terms: legal@simulationlabs.example.</P>
    </LegalLayout>
  );
}
