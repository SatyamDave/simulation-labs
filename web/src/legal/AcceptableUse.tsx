// Acceptable Use & Refund Policy — public route /legal/acceptable-use. DRAFT.

import LegalLayout, { H2, P, UL, LI, B } from "./LegalLayout";

export default function AcceptableUse() {
  return (
    <LegalLayout title="Acceptable Use & Refund Policy" updated="July 2026">
      <P>
        This policy is part of the Terms of Service. It describes how you may use
        the Simulation Labs Service and our cancellation and refund terms.
      </P>

      <H2>Authorization: test only what you control</H2>
      <P>
        Simulation Labs drives autonomous browser agents against a live website
        of your choosing. This is powerful, and it carries real responsibility.
      </P>
      <UL>
        <LI>
          <B>
            You may only run simulations against a website you own or that you
            have explicit, documented permission to test.
          </B>
        </LI>
        <LI>
          Each run requires you to attest to your authorization for that specific
          target. We record who attested, when, and for which domain.
        </LI>
        <LI>
          Do not use the Service to probe, load-test, scrape, or attack sites you
          do not control, to evade access controls, or in any way that violates a
          target site's terms or applicable computer-misuse, anti-hacking, or
          data-protection laws.
        </LI>
      </UL>
      <P>
        We may refuse, throttle, or terminate runs and accounts we reasonably
        believe are unauthorized or unlawful, and we may cooperate with lawful
        requests.
      </P>

      <H2>Prohibited uses</H2>
      <UL>
        <LI>Testing third-party sites without permission.</LI>
        <LI>Targeting internal, loopback, or cloud-metadata endpoints, or otherwise attempting to reach systems that are not legitimate public test targets.</LI>
        <LI>Excessive or abusive request volumes intended to degrade a target site.</LI>
        <LI>Capturing or exfiltrating personal data you are not entitled to process.</LI>
        <LI>Reverse engineering, reselling, or using the Service to build a competing product.</LI>
        <LI>Interfering with the Service's security, integrity, or other customers' use.</LI>
      </UL>

      <H2>Responsible operation</H2>
      <UL>
        <LI>Prefer staging environments and test accounts where possible.</LI>
        <LI>Keep API keys secret and scoped; rotate them if exposed.</LI>
        <LI>Respect your own plan's rate and usage limits.</LI>
      </UL>

      <H2>Plans and cancellation</H2>
      <UL>
        <LI>
          Paid subscriptions renew automatically for the plan term (for example,
          monthly) until cancelled.
        </LI>
        <LI>
          You can cancel at any time from your billing settings. Cancellation
          stops the next renewal; your plan remains active through the end of the
          current paid period.
        </LI>
        <LI>
          Downgrades take effect at the next renewal unless stated otherwise.
        </LI>
      </UL>

      <H2>Refunds</H2>
      <UL>
        <LI>
          Fees are generally non-refundable, including for partial billing
          periods and unused runs, except as required by law or as expressly
          stated here.
        </LI>
        <LI>
          <B>14-day first-purchase guarantee:</B> if you are not satisfied with
          your first paid subscription, contact us within 14 days of that initial
          charge for a full refund of that charge.
        </LI>
        <LI>
          <B>Service-failure refunds:</B> if a sustained failure on our side
          prevents you from running simulations, contact support and we will work
          in good faith toward a prorated credit or refund for the affected
          period.
        </LI>
        <LI>
          Refunds are issued to the original payment method through our payment
          processor and may take several business days to appear.
        </LI>
      </UL>

      <H2>How to cancel or request a refund</H2>
      <P>
        Cancel from your dashboard billing settings, or contact
        billing@simulationlabs.example. For refund requests, include your account
        email and the charge in question.
      </P>

      <H2>Enforcement</H2>
      <P>
        Violations of this policy may result in suspension or termination without
        refund, in addition to any other remedies available to us. [Confirm final
        refund windows and enforcement steps with legal counsel before launch.]
      </P>
    </LegalLayout>
  );
}
