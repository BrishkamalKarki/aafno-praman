// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title CredentialRegistry
 * @notice Append-only anchor registry for academic credentials and employment
 *         records issued in Nepal.
 *
 * Design constraints that shaped this contract:
 *
 *  1. NO PERSONAL DATA ON CHAIN. The contract stores `keccak256` of a
 *     canonicalised record and nothing else about the subject. A name, a
 *     registration number or a CGPA must never reach this file. Issuer
 *     organisation names are stored because they are public business
 *     identities, not personal data.
 *
 *  2. WRITES ARE PERMISSIONED, READS ARE OPEN. Only an issuer that the
 *     registrar has approved can anchor. Anyone at all can verify.
 *
 *  3. SUSPENSION IS NOT RETROACTIVE. When an issuer is suspended, records it
 *     anchored while in good standing stay valid. Callers get `issuerActive`
 *     and `issuerSuspendedAt` so they can present that nuance rather than
 *     silently invalidating a graduate's degree.
 *
 *  4. IMMUTABLE IS NOT UNCORRECTABLE. Anchors cannot be deleted, but they can
 *     be revoked (with a reason) or superseded by a corrected anchor. Both are
 *     additive state transitions, so history stays auditable.
 */
contract CredentialRegistry {
    // ---------------------------------------------------------------- types

    enum IssuerKind {
        None, // 0 — never registered
        Institution, // 1 — university / college, issues academic credentials
        Employer // 2 — company, issues employment records
    }

    struct Issuer {
        IssuerKind kind;
        bool active;
        uint64 approvedAt;
        uint64 suspendedAt; // 0 while in good standing
        string name; // public legal name, e.g. "Tribhuvan University"
    }

    struct Anchor {
        address issuer;
        uint64 issuedAt;
        uint64 revokedAt; // 0 unless revoked
        bytes32 supersededBy; // 0x0 unless amended
    }

    /// @notice Everything a verifier needs, in a single call.
    struct Verification {
        bool exists;
        address issuer;
        string issuerName;
        IssuerKind issuerKind;
        bool issuerActive;
        uint64 issuerSuspendedAt;
        uint64 issuedAt;
        bool revoked;
        uint64 revokedAt;
        string revocationReason;
        bytes32 supersededBy;
    }

    // ---------------------------------------------------------------- state

    address public registrar;
    address public pendingRegistrar;

    mapping(address => Issuer) private _issuers;
    mapping(bytes32 => Anchor) private _anchors;
    mapping(bytes32 => string) private _revocationReasons;

    /// @dev Enumerable so the demo explorer and reconciliation jobs can walk
    ///      the full set without an off-chain indexer.
    bytes32[] private _anchorIndex;
    address[] private _issuerIndex;

    // --------------------------------------------------------------- events

    event RegistrarTransferStarted(address indexed from, address indexed to);
    event RegistrarTransferred(address indexed from, address indexed to);
    event IssuerApproved(address indexed issuer, IssuerKind kind, string name, uint64 at);
    event IssuerSuspended(address indexed issuer, string reason, uint64 at);
    event IssuerReinstated(address indexed issuer, uint64 at);
    event RecordAnchored(bytes32 indexed recordHash, address indexed issuer, uint64 at);
    event RecordRevoked(bytes32 indexed recordHash, address indexed by, string reason, uint64 at);
    event RecordSuperseded(bytes32 indexed oldHash, bytes32 indexed newHash, address indexed by, uint64 at);

    // --------------------------------------------------------------- errors

    error NotRegistrar();
    error NotPendingRegistrar();
    error ZeroAddress();
    error IssuerNotApproved(address issuer);
    error IssuerSuspendedError(address issuer);
    error IssuerAlreadyApproved(address issuer);
    error InvalidIssuerKind();
    error EmptyName();
    error ZeroHash();
    error AlreadyAnchored(bytes32 recordHash);
    error NotAnchored(bytes32 recordHash);
    error AlreadyRevoked(bytes32 recordHash);
    error AlreadySuperseded(bytes32 recordHash);
    error NotRecordIssuer(bytes32 recordHash, address caller);
    error EmptyBatch();
    error BatchTooLarge(uint256 size, uint256 max);
    error EmptyReason();

    /// @dev Bounded so a batch can never exceed the block gas limit and strand
    ///      a registrar's bulk upload halfway through.
    uint256 public constant MAX_BATCH = 200;

    // ------------------------------------------------------------ modifiers

    modifier onlyRegistrar() {
        if (msg.sender != registrar) revert NotRegistrar();
        _;
    }

    /// @dev Anchoring requires an issuer in *current* good standing. Reading a
    ///      previously anchored record does not.
    modifier onlyActiveIssuer() {
        Issuer storage issuer = _issuers[msg.sender];
        if (issuer.kind == IssuerKind.None) revert IssuerNotApproved(msg.sender);
        if (!issuer.active) revert IssuerSuspendedError(msg.sender);
        _;
    }

    constructor(address initialRegistrar) {
        if (initialRegistrar == address(0)) revert ZeroAddress();
        registrar = initialRegistrar;
        emit RegistrarTransferred(address(0), initialRegistrar);
    }

    // ------------------------------------------------- registrar governance

    /**
     * @notice Begin handing the root of trust to a new registrar.
     * @dev Two-step on purpose. A single-step transfer to a typo'd address
     *      would permanently freeze issuer onboarding, and there is no
     *      recovery path in an append-only registry.
     */
    function transferRegistrar(address newRegistrar) external onlyRegistrar {
        if (newRegistrar == address(0)) revert ZeroAddress();
        pendingRegistrar = newRegistrar;
        emit RegistrarTransferStarted(registrar, newRegistrar);
    }

    function acceptRegistrar() external {
        if (msg.sender != pendingRegistrar) revert NotPendingRegistrar();
        address previous = registrar;
        registrar = pendingRegistrar;
        pendingRegistrar = address(0);
        emit RegistrarTransferred(previous, registrar);
    }

    // --------------------------------------------------- issuer lifecycle

    /**
     * @notice Approve an organisation to anchor records.
     * @param issuerAddress Custodial signing address the platform generated.
     * @param kind          Institution or Employer.
     * @param name          Public legal name, shown to verifiers.
     */
    function approveIssuer(address issuerAddress, IssuerKind kind, string calldata name) external onlyRegistrar {
        if (issuerAddress == address(0)) revert ZeroAddress();
        if (kind == IssuerKind.None) revert InvalidIssuerKind();
        if (bytes(name).length == 0) revert EmptyName();
        if (_issuers[issuerAddress].kind != IssuerKind.None) revert IssuerAlreadyApproved(issuerAddress);

        uint64 now64 = uint64(block.timestamp);
        _issuers[issuerAddress] =
            Issuer({kind: kind, active: true, approvedAt: now64, suspendedAt: 0, name: name});
        _issuerIndex.push(issuerAddress);

        emit IssuerApproved(issuerAddress, kind, name, now64);
    }

    function suspendIssuer(address issuerAddress, string calldata reason) external onlyRegistrar {
        Issuer storage issuer = _issuers[issuerAddress];
        if (issuer.kind == IssuerKind.None) revert IssuerNotApproved(issuerAddress);
        if (!issuer.active) revert IssuerSuspendedError(issuerAddress);
        if (bytes(reason).length == 0) revert EmptyReason();

        issuer.active = false;
        issuer.suspendedAt = uint64(block.timestamp);
        emit IssuerSuspended(issuerAddress, reason, issuer.suspendedAt);
    }

    function reinstateIssuer(address issuerAddress) external onlyRegistrar {
        Issuer storage issuer = _issuers[issuerAddress];
        if (issuer.kind == IssuerKind.None) revert IssuerNotApproved(issuerAddress);
        issuer.active = true;
        issuer.suspendedAt = 0;
        emit IssuerReinstated(issuerAddress, uint64(block.timestamp));
    }

    // ------------------------------------------------------------ anchoring

    /**
     * @notice Anchor one canonical record hash.
     * @dev Reverting on a duplicate is the contract-level idempotency guard:
     *      re-uploading the same graduation CSV cannot mint a second anchor,
     *      and the backend surfaces the existing one instead.
     */
    function anchor(bytes32 recordHash) external onlyActiveIssuer {
        _anchor(recordHash, msg.sender);
    }

    /**
     * @notice Anchor a whole graduating batch in one transaction.
     * @dev A registrar uploading 180 graduates should pay for one transaction,
     *      not 180. Reverts atomically so a partially written batch never
     *      leaves the off-chain records in an ambiguous state.
     */
    function anchorBatch(bytes32[] calldata recordHashes) external onlyActiveIssuer {
        uint256 count = recordHashes.length;
        if (count == 0) revert EmptyBatch();
        if (count > MAX_BATCH) revert BatchTooLarge(count, MAX_BATCH);
        for (uint256 i = 0; i < count; ++i) {
            _anchor(recordHashes[i], msg.sender);
        }
    }

    function _anchor(bytes32 recordHash, address issuerAddress) private {
        if (recordHash == bytes32(0)) revert ZeroHash();
        if (_anchors[recordHash].issuedAt != 0) revert AlreadyAnchored(recordHash);

        uint64 now64 = uint64(block.timestamp);
        _anchors[recordHash] =
            Anchor({issuer: issuerAddress, issuedAt: now64, revokedAt: 0, supersededBy: bytes32(0)});
        _anchorIndex.push(recordHash);

        emit RecordAnchored(recordHash, issuerAddress, now64);
    }

    // ----------------------------------------------------------- corrections

    /**
     * @notice Revoke a record. Callable by the original issuer, or by the
     *         registrar when an issuer is uncooperative or defunct.
     * @dev A suspended issuer may still revoke. Suspension is usually the
     *      moment fraudulent anchors need cleaning up, so blocking revocation
     *      here would be exactly backwards.
     */
    function revoke(bytes32 recordHash, string calldata reason) external {
        Anchor storage record = _anchors[recordHash];
        if (record.issuedAt == 0) revert NotAnchored(recordHash);
        if (record.revokedAt != 0) revert AlreadyRevoked(recordHash);
        if (msg.sender != record.issuer && msg.sender != registrar) {
            revert NotRecordIssuer(recordHash, msg.sender);
        }
        if (bytes(reason).length == 0) revert EmptyReason();

        record.revokedAt = uint64(block.timestamp);
        _revocationReasons[recordHash] = reason;
        emit RecordRevoked(recordHash, msg.sender, reason, record.revokedAt);
    }

    /**
     * @notice Replace a record with a corrected one, anchoring the correction
     *         and linking the old anchor forward in a single transaction.
     * @dev For honest mistakes — a misspelled name, a wrong tenure end date.
     *      The old hash keeps resolving so an already-issued QR code degrades
     *      to "superseded, here is the current record" rather than dead-ending.
     */
    function supersede(bytes32 oldHash, bytes32 newHash) external onlyActiveIssuer {
        Anchor storage old = _anchors[oldHash];
        if (old.issuedAt == 0) revert NotAnchored(oldHash);
        if (old.supersededBy != bytes32(0)) revert AlreadySuperseded(oldHash);
        if (msg.sender != old.issuer) revert NotRecordIssuer(oldHash, msg.sender);

        _anchor(newHash, msg.sender);
        old.supersededBy = newHash;
        emit RecordSuperseded(oldHash, newHash, msg.sender, uint64(block.timestamp));
    }

    // ------------------------------------------------------------- read path

    /**
     * @notice One-call verification. Free to call, no account, no gas.
     * @return A fully populated struct; `exists == false` means not found and
     *         is deliberately indistinguishable from "never issued" so the
     *         registry cannot be enumerated by probing.
     */
    function verify(bytes32 recordHash) external view returns (Verification memory) {
        Anchor storage record = _anchors[recordHash];
        if (record.issuedAt == 0) {
            return Verification({
                exists: false,
                issuer: address(0),
                issuerName: "",
                issuerKind: IssuerKind.None,
                issuerActive: false,
                issuerSuspendedAt: 0,
                issuedAt: 0,
                revoked: false,
                revokedAt: 0,
                revocationReason: "",
                supersededBy: bytes32(0)
            });
        }

        Issuer storage issuer = _issuers[record.issuer];
        return Verification({
            exists: true,
            issuer: record.issuer,
            issuerName: issuer.name,
            issuerKind: issuer.kind,
            issuerActive: issuer.active,
            issuerSuspendedAt: issuer.suspendedAt,
            issuedAt: record.issuedAt,
            revoked: record.revokedAt != 0,
            revokedAt: record.revokedAt,
            revocationReason: _revocationReasons[recordHash],
            supersededBy: record.supersededBy
        });
    }

    /// @notice Cheap existence probe for the anchor-retry reconciliation job.
    function isAnchored(bytes32 recordHash) external view returns (bool) {
        return _anchors[recordHash].issuedAt != 0;
    }

    function getIssuer(address issuerAddress) external view returns (Issuer memory) {
        return _issuers[issuerAddress];
    }

    function canAnchor(address issuerAddress) external view returns (bool) {
        Issuer storage issuer = _issuers[issuerAddress];
        return issuer.kind != IssuerKind.None && issuer.active;
    }

    function anchorCount() external view returns (uint256) {
        return _anchorIndex.length;
    }

    function anchorAt(uint256 index) external view returns (bytes32) {
        return _anchorIndex[index];
    }

    function issuerCount() external view returns (uint256) {
        return _issuerIndex.length;
    }

    function issuerAt(uint256 index) external view returns (address) {
        return _issuerIndex[index];
    }
}
