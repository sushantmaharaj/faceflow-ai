// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ContentRegistry
 * @notice Registers and verifies SHA-256 content fingerprints on Ethereum Sepolia.
 *         Each fingerprint (bytes32) is stored exactly once with a block timestamp.
 *         Once registered, fingerprints cannot be modified — enforcing tamper-evidence.
 *
 * Deployment: Use Remix IDE → compile with 0.8.20 → deploy on Injected Provider (MetaMask Sepolia).
 */
contract ContentRegistry {
    /// @notice Maps fingerprint → unix timestamp of registration (0 = not registered)
    mapping(bytes32 => uint256) public registeredAt;

    /// @notice Emitted on each successful registration
    event ContentRegistered(
        bytes32 indexed fingerprint,
        uint256 timestamp,
        address indexed submitter
    );

    /**
     * @notice Register a content fingerprint.
     * @param fingerprint SHA-256 hash as bytes32 (first registration only).
     * @dev Reverts if fingerprint was already registered.
     */
    function register(bytes32 fingerprint) external {
        require(
            registeredAt[fingerprint] == 0,
            "Fingerprint already registered"
        );

        registeredAt[fingerprint] = block.timestamp;

        emit ContentRegistered(
            fingerprint,
            block.timestamp,
            msg.sender
        );
    }

    /**
     * @notice Check if a fingerprint is registered and when.
     * @param fingerprint SHA-256 hash as bytes32.
     * @return found True if registered.
     * @return timestamp Unix timestamp of registration (0 if not found).
     */
    function verify(bytes32 fingerprint)
        external
        view
        returns (bool found, uint256 timestamp)
    {
        timestamp = registeredAt[fingerprint];
        found = timestamp != 0;
    }
}
